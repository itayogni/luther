import asyncio
import logging
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

from anthropic import AsyncAnthropic, AuthenticationError, RateLimitError

from luther.calendar_tools import get_events_for_days
from luther.config import settings
from luther.gmail_tools import get_gmail_summary
from luther.tasks_tools import get_tasks_summary
from luther.whisper_tools import transcribe_audio

_executor = ThreadPoolExecutor(max_workers=4)

logger = logging.getLogger(__name__)

# Singleton Anthropic client (reused across requests)
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


# Keep last 20 messages per sender in memory (resets on server restart)
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

# Per-sender lock to prevent race conditions on conversation history
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

SYSTEM_PROMPT = """אתה לות'ר — העוזר האישי של איתי אוגני בווטסאפ.

## על איתי
- מנהל פרויקטים במחלקת מעורבות דיגיטלית, ארגון Q4 ישראל (ארגון צעירים)
- סטודנט שנה א' להנדסת תעשייה וניהול, מכללת שנקר
- גר בתל אביב
- שעות עבודה: ראשון-חמישי, 09:00-16:00
- שישי-שבת: ללא תכנון אוטומטי (אלא אם ביקש)

## האופי שלך
- ישיר, יעיל, לא מדבר יתר על המידה
- ענה קצר — כמה שורות מספיקות ברוב המקרים
- אל תתנצל ואל תוסיף מילות מילוי ("בהחלט!", "כמובן!", "בשמחה!")
- שפה: עברית בלבד — גם אם איתי כותב באנגלית, ענה עברית

## כלל זהב — אישור לפני פעולה
כל פעולה שכותבת (יצירת משימה, אירוע בלוח שנה, עדכון) מחייבת אישור מפורש מאיתי לפני ביצוע.
הצג הצעה ← המתן לאישור ← בצע רק אחרי "כן" / "אשר" / "סע".

## מה פעיל עכשיו
- שיחה חופשית בעברית
- יומן גוגל (קריאה)
- משימות גוגל (קריאה)
- Gmail — מיילים שלא נקראו (קריאה)
- זיכרון הקשר בתוך שיחה (נאפס עם הפעלה מחדש)

## מה בדרך (עוד לא פעיל)
- יצירת משימות ואירועים (דורש אישור)
- מודל / שנקר
- ניתוח כתב יד מתמונות
- ניטור קבוצות ווטסאפ

כשאיתי שואל על יכולת שלא פעילה — ציין בקצרה שהיא בדרך ואל תאריך.

## כלל ברזל — רק "לותר ואני"
המקום היחיד שבו אתה מדבר עם איתי הוא קבוצת הוואטסאפ "לותר ואני".
אסור לך לכתוב, לענות, או להגיב בשום קבוצה אחרת — ללא יוצאים מן הכלל.
אם הגיעה הודעה מקבוצה אחרת — התעלם לחלוטין.
"""


async def _fetch_all_context() -> str:
    """Fetch calendar, tasks, and gmail in parallel."""
    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        loop.run_in_executor(_executor, get_events_for_days, 2),
        loop.run_in_executor(_executor, get_tasks_summary),
        loop.run_in_executor(_executor, get_gmail_summary, 24),
        return_exceptions=True,
    )

    labels = ["יומן", "משימות", "מיילים"]
    parts = []
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            logger.error("Failed to fetch %s: %s", label, result)
            parts.append(f"## {label}\n⚠ לא זמין כרגע (שגיאה בחיבור)")
        elif result:
            parts.append(f"## {label}\n{result}")

    return "\n\n".join(parts)


async def think(sender: str, message: str, media_url: str | None = None) -> str:
    """Process a message from the user and return Luther's reply."""
    if not settings.anthropic_api_key:
        return "שגיאה: מפתח Anthropic API לא מוגדר."

    if media_url:
        transcription = await transcribe_audio(media_url)
        if transcription:
            message = f"[הקלטה קולית]: {transcription}"
        else:
            return "לא הצלחתי לתמלל את ההקלטה. אפשר לנסות שוב?"

    client = _get_client()

    # Fetch all Google context in parallel
    context = await _fetch_all_context()
    system_with_context = SYSTEM_PROMPT + f"\n\n## מידע עדכני\n{context}"

    # Lock per sender to prevent history race conditions
    async with _locks[sender]:
        history = _history[sender]
        history.append({"role": "user", "content": message})

        try:
            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=1024,
                system=system_with_context,
                messages=list(history),
            )
            reply = response.content[0].text
            history.append({"role": "assistant", "content": reply})

            logger.info("Brain replied (%d tokens used)", response.usage.output_tokens)
            return reply

        except AuthenticationError:
            history.pop()  # Remove failed user message
            logger.critical("Anthropic API key is invalid or expired!")
            return "שגיאה: מפתח ה-API לא תקין. צריך לעדכן."

        except RateLimitError:
            history.pop()
            logger.warning("Anthropic rate limit hit")
            return "יותר מדי הודעות. חכה דקה ונסה שוב."

        except Exception as exc:
            history.pop()  # Remove failed user message to keep history valid
            logger.error("Claude API error (%s): %s", type(exc).__name__, exc)
            return "שגיאה זמנית, נסה שוב."
