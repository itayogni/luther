import asyncio
import logging
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

from anthropic import AsyncAnthropic, AuthenticationError, RateLimitError

from luther.calendar_tools import create_event, delete_event, get_events_for_days
from luther.config import settings
from luther.gmail_tools import get_gmail_summary
from luther.tasks_tools import complete_task, create_task, get_tasks_summary
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
_locks: dict[str, asyncio.Lock] = {}

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

## מה פעיל
- שיחה חופשית בעברית
- יומן גוגל (קריאה + כתיבה)
- משימות גוגל (קריאה + יצירה + השלמה)
- Gmail — מיילים שלא נקראו (קריאה)
- זיכרון הקשר בתוך שיחה (נאפס עם הפעלה מחדש)

## שימוש בכלים
יש לך כלים ליצירת אירועים ומשימות. השתמש בהם כשאיתי מבקש.
התאריך היום מוזרק בתחתית ההודעה — השתמש בו כדי לחשב "מחר", "יום שלישי הבא" וכו'.
כשאתה יוצר אירוע, חשב את שעת הסיום (ברירת מחדל: שעה אחרי ההתחלה).
פורמט תאריך לאירועים: ISO 8601 עם timezone ישראל (למשל 2026-05-18T10:00:00+03:00).
פורמט תאריך למשימות: ISO 8601 UTC (למשל 2026-05-18T00:00:00Z).

## כלל ברזל — רק "לותר ואני"
המקום היחיד שבו אתה מדבר עם איתי הוא קבוצת הוואטסאפ "לותר ואני".
אסור לך לכתוב, לענות, או להגיב בשום קבוצה אחרת — ללא יוצאים מן הכלל.
אם הגיעה הודעה מקבוצה אחרת — התעלם לחלוטין.
"""


import json
from datetime import datetime
from zoneinfo import ZoneInfo

TOOLS = [
    {
        "name": "create_event",
        "description": "יצירת אירוע חדש ביומן גוגל",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "שם האירוע"},
                "start_time": {"type": "string", "description": "שעת התחלה בפורמט ISO 8601 (למשל 2026-05-18T10:00:00+03:00)"},
                "end_time": {"type": "string", "description": "שעת סיום בפורמט ISO 8601"},
                "account_name": {"type": "string", "description": "חשבון: עבודה או אישי", "default": "אישי"},
                "location": {"type": "string", "description": "מיקום (אופציונלי)", "default": ""},
                "description": {"type": "string", "description": "תיאור (אופציונלי)", "default": ""},
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
    {
        "name": "create_task",
        "description": "יצירת משימה חדשה ב-Google Tasks",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "שם המשימה"},
                "notes": {"type": "string", "description": "הערות (אופציונלי)", "default": ""},
                "due_date": {"type": "string", "description": "תאריך יעד בפורמט ISO 8601 UTC (למשל 2026-05-18T00:00:00Z)", "default": ""},
                "account_name": {"type": "string", "description": "חשבון: עבודה או אישי", "default": "אישי"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_task",
        "description": "סימון משימה כהושלמה (לפי שם)",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "שם המשימה (או חלק ממנו)"},
                "account_name": {"type": "string", "description": "חשבון: עבודה או אישי", "default": "אישי"},
            },
            "required": ["title"],
        },
    },
]

TOOL_HANDLERS = {
    "create_event": lambda args: create_event(**args),
    "create_task": lambda args: create_task(**args),
    "complete_task": lambda args: complete_task(**args),
}


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
    now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    date_line = f"\n\nהתאריך והשעה עכשיו: {now.strftime('%A %Y-%m-%d %H:%M')} (Asia/Jerusalem)"
    system_with_context = SYSTEM_PROMPT + f"\n\n## מידע עדכני\n{context}" + date_line

    # Lock per sender to prevent history race conditions
    if sender not in _locks:
        _locks[sender] = asyncio.Lock()
    async with _locks[sender]:
        history = _history[sender]
        history.append({"role": "user", "content": message})

        try:
            # Tool use loop — Claude may call tools before giving a final text reply
            loop = asyncio.get_event_loop()
            for _round in range(5):  # max 5 tool calls per message
                response = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=1024,
                    system=system_with_context,
                    messages=list(history),
                    tools=TOOLS,
                )

                # If Claude just responds with text, we're done
                if response.stop_reason == "end_turn":
                    text_parts = [b.text for b in response.content if b.type == "text"]
                    reply = "\n".join(text_parts) or ""
                    history.append({"role": "assistant", "content": response.content})
                    logger.info("Brain replied (%d tokens)", response.usage.output_tokens)
                    return reply

                # If Claude wants to call a tool
                if response.stop_reason == "tool_use":
                    history.append({"role": "assistant", "content": response.content})

                    tool_results = []
                    for block in response.content:
                        if block.type != "tool_use":
                            continue
                        handler = TOOL_HANDLERS.get(block.name)
                        if handler:
                            logger.info("Tool call: %s(%s)", block.name, json.dumps(block.input, ensure_ascii=False))
                            result = await loop.run_in_executor(_executor, handler, block.input)
                        else:
                            result = f"כלי לא מוכר: {block.name}"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                    history.append({"role": "user", "content": tool_results})
                    continue  # Let Claude process the tool results

                # Unexpected stop reason — return whatever text we have
                text_parts = [b.text for b in response.content if b.type == "text"]
                reply = "\n".join(text_parts) or "לא הצלחתי לעבד את הבקשה."
                history.append({"role": "assistant", "content": response.content})
                return reply

            return "יותר מדי פעולות. נסה לפשט את הבקשה."

        except AuthenticationError:
            history.pop()
            logger.critical("Anthropic API key is invalid or expired!")
            return "שגיאה: מפתח ה-API לא תקין. צריך לעדכן."

        except RateLimitError:
            history.pop()
            logger.warning("Anthropic rate limit hit")
            return "יותר מדי הודעות. חכה דקה ונסה שוב."

        except Exception as exc:
            history.pop()
            logger.error("Claude API error (%s): %s", type(exc).__name__, exc)
            return "שגיאה זמנית, נסה שוב."
