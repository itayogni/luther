import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.discovery import build

from luther.auth import ACCOUNTS, get_credentials

logger = logging.getLogger(__name__)

ISRAEL_TZ = timezone(timedelta(hours=3))
HEBREW_DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]
HEBREW_MONTHS = [
    "", "ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
    "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר",
]
_PY_TO_HEB = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}


def _format_time(dt_str: str, is_all_day: bool) -> str:
    if is_all_day:
        return "כל היום"
    try:
        return datetime.fromisoformat(dt_str).astimezone(ISRAEL_TZ).strftime("%H:%M")
    except Exception:
        return dt_str


def _format_date_hebrew(dt: datetime) -> str:
    heb_day = HEBREW_DAYS[_PY_TO_HEB[dt.weekday()]]
    return f"{heb_day} {dt.day} {HEBREW_MONTHS[dt.month]}"


def _fetch_events_for_account(account: dict, days: int) -> list[dict]:
    try:
        creds = get_credentials(account["token"])
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(ISRAEL_TZ)

        result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days)).isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=20,
        ).execute()

        events = []
        for ev in result.get("items", []):
            start = ev.get("start", {})
            is_all_day = "date" in start and "dateTime" not in start
            dt_str = start.get("dateTime") or start.get("date", "")

            if is_all_day:
                dt = datetime.fromisoformat(start["date"]).replace(tzinfo=ISRAEL_TZ)
            else:
                dt = datetime.fromisoformat(dt_str).astimezone(ISRAEL_TZ)

            events.append({
                "dt": dt,
                "time_str": _format_time(dt_str, is_all_day),
                "summary": ev.get("summary", "(ללא שם)"),
                "location": ev.get("location", ""),
                "account": account["name"],
            })
        return events

    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.error("Calendar error for '%s': %s", account["name"], exc)
        return []


def get_events_for_days(days: int = 2) -> str:
    all_events: list[dict] = []
    missing = []

    for account in ACCOUNTS:
        if not account["token"].exists():
            missing.append(account["name"])
            continue
        all_events.extend(_fetch_events_for_account(account, days))

    if not all_events:
        return "אין אירועים ביומן ל-48 השעות הקרובות."

    all_events.sort(key=lambda e: e["dt"])

    lines = ["יומן — 48 שעות קרובות:"]
    current_date_str = ""

    for ev in all_events:
        date_str = _format_date_hebrew(ev["dt"])
        if date_str != current_date_str:
            current_date_str = date_str
            lines.append(f"\n{date_str}:")

        line = f"  [{ev['account']}] {ev['time_str']} — {ev['summary']}"
        if ev["location"]:
            line += f" ({ev['location']})"
        lines.append(line)

    return "\n".join(lines)
