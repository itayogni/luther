import asyncio
import json
import logging
import re
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

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


# Keep last 10 messages per sender
_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))

# Per-sender lock to prevent race conditions on conversation history
_locks: dict[str, asyncio.Lock] = {}

# --- Context keywords: split by source for focused loading ---
_CAL_KEYWORDS = re.compile(
    r"יומן|לוח|פגישה|אירוע|מתי|מחר|היום|השבוע|schedule|calendar|קבע|תקבע|תמחק|תזיז",
    re.IGNORECASE,
)
_TASK_KEYWORDS = re.compile(
    r"משימה|task|תזכור|סמן.*בוצע|השלם|מה יש לי|תכנן|תוסיף.*משימה|תזכיר",
    re.IGNORECASE,
)
_MAIL_KEYWORDS = re.compile(
    r"מייל|mail|gmail|דואר",
    re.IGNORECASE,
)

# Simple confirmation pattern — skip full API call
_CONFIRM_PATTERN = re.compile(
    r"^(כן|סע|אשר|מאשר|מאושר|אישור|בצע|עשה|יאללה|יש|ok|yes|sure|👍)\s*[.!]?\s*$",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """אתה לות'ר — עוזר אישי של איתי בוואטסאפ. עברית בלבד, קצר וישיר.

איתי: מנהל פרויקטים ב-Q4 ישראל, סטודנט הנדסת תעשייה בשנקר, תל אביב.
עבודה: א-ה 09-16. שישי-שבת ללא תכנון אלא אם ביקש.

כללים:
- אישור לפני כל פעולה (הצעה → אישור → ביצוע)
- שפה: עברית בלבד
- אופי: ישיר, ללא מילות מילוי
- כלים: יומן + משימות + מיילים (קריאה)

תאריכים: ISO 8601, timezone ישראל לאירועים, UTC למשימות.
ברירת מחדל: אירוע = שעה, חשבון = אישי.
"""


TOOLS = [
    {
        "name": "create_event",
        "description": "יצירת אירוע ביומן (עם אפשרות להזמין משתתפים)",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "שם האירוע"},
                "start_time": {"type": "string", "description": "התחלה ISO 8601"},
                "end_time": {"type": "string", "description": "סיום ISO 8601"},
                "account_name": {"type": "string", "default": "אישי"},
                "location": {"type": "string", "default": ""},
                "description": {"type": "string", "default": ""},
                "attendees": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "רשימת כתובות מייל של מוזמנים",
                    "default": [],
                },
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
    {
        "name": "create_task",
        "description": "יצירת משימה",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "שם המשימה"},
                "notes": {"type": "string", "default": ""},
                "due_date": {"type": "string", "default": ""},
                "account_name": {"type": "string", "default": "אישי"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "complete_task",
        "description": "סימון משימה כהושלמה",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "שם המשימה (או חלק)"},
                "account_name": {"type": "string", "default": "אישי"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "delete_event",
        "description": "מחיקת אירוע מיומן",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "מזהה האירוע"},
                "account_name": {"type": "string", "default": "אישי"},
            },
            "required": ["event_id"],
        },
    },
]

TOOL_HANDLERS = {
    "create_event": lambda args: create_event(**args),
    "create_task": lambda args: create_task(**args),
    "complete_task": lambda args: complete_task(**args),
    "delete_event": lambda args: delete_event(**args),
}


async def _fetch_focused_context(message: str) -> str:
    """Fetch only the Google context that's relevant to the message."""
    loop = asyncio.get_event_loop()
    tasks = []
    labels = []

    if _CAL_KEYWORDS.search(message):
        tasks.append(loop.run_in_executor(_executor, get_events_for_days, 2))
        labels.append("יומן")
    if _TASK_KEYWORDS.search(message):
        tasks.append(loop.run_in_executor(_executor, get_tasks_summary))
        labels.append("משימות")
    if _MAIL_KEYWORDS.search(message):
        tasks.append(loop.run_in_executor(_executor, get_gmail_summary, 24))
        labels.append("מיילים")

    if not tasks:
        return ""

    results = await asyncio.gather(*tasks, return_exceptions=True)

    parts = []
    for label, result in zip(labels, results):
        if isinstance(result, Exception):
            logger.error("Failed to fetch %s: %s", label, result)
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

    # Focused context: only fetch what's needed
    context = await _fetch_focused_context(message)

    now = datetime.now(ZoneInfo("Asia/Jerusalem"))
    date_line = f"עכשיו: {now.strftime('%A %Y-%m-%d %H:%M')} (Israel)"

    # Build system prompt with prompt caching
    system_blocks = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": (f"\n\n{context}\n\n{date_line}" if context else f"\n\n{date_line}"),
        },
    ]

    # Lock per sender to prevent history race conditions
    if sender not in _locks:
        _locks[sender] = asyncio.Lock()
    async with _locks[sender]:
        history = _history[sender]
        history.append({"role": "user", "content": message})

        try:
            loop = asyncio.get_event_loop()
            for _round in range(5):  # max 5 tool calls per message
                response = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=512,
                    system=system_blocks,
                    messages=list(history),
                    tools=TOOLS,
                )

                # If Claude just responds with text, we're done
                if response.stop_reason == "end_turn":
                    text_parts = [b.text for b in response.content if b.type == "text"]
                    reply = "\n".join(text_parts) or ""
                    history.append({"role": "assistant", "content": response.content})
                    return reply

                # If Claude wants to call a tool — execute and return result directly
                if response.stop_reason == "tool_use":
                    history.append({"role": "assistant", "content": response.content})

                    results_text = []
                    tool_results = []
                    for block in response.content:
                        if block.type != "tool_use":
                            continue
                        handler = TOOL_HANDLERS.get(block.name)
                        if handler:
                            logger.info("Tool: %s(%s)", block.name, json.dumps(block.input, ensure_ascii=False))
                            result = await loop.run_in_executor(_executor, handler, block.input)
                        else:
                            result = f"כלי לא מוכר: {block.name}"
                        results_text.append(result)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })

                    # Return tool result directly with ✅ — skip extra API call
                    confirmation = "✅ " + " | ".join(results_text)
                    # Store in history as if Claude responded (for context continuity)
                    history.append({"role": "user", "content": tool_results})
                    history.append({"role": "assistant", "content": confirmation})
                    return confirmation

                # Unexpected stop reason
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
