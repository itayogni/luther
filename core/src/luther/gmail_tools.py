import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from luther.auth import ACCOUNTS, get_credentials

logger = logging.getLogger(__name__)

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")


def _decode_header_value(value: str) -> str:
    """Decode email header (handles UTF-8 encoded subjects)."""
    import email.header
    parts = email.header.decode_header(value)
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _get_header(headers: list, name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return _decode_header_value(h["value"])
    return ""


def _fetch_emails_for_account(account: dict, hours: int = 24) -> list[dict]:
    try:
        creds = get_credentials(account["token"])
        service = build("gmail", "v1", credentials=creds)

        # Search unread emails from last N hours
        after_ts = int((datetime.now(ISRAEL_TZ) - timedelta(hours=hours)).timestamp())
        query = f"is:unread after:{after_ts}"

        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=15,
        ).execute()

        messages = result.get("messages", [])
        emails = []

        for msg in messages:
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = detail.get("payload", {}).get("headers", [])
            subject = _get_header(headers, "Subject") or "(ללא נושא)"
            sender = _get_header(headers, "From")
            date_str = _get_header(headers, "Date")

            # Parse sender name only (not full email)
            if "<" in sender:
                sender = sender.split("<")[0].strip().strip('"')

            # Parse date
            try:
                dt = parsedate_to_datetime(date_str).astimezone(ISRAEL_TZ)
                time_label = dt.strftime("%H:%M")
            except Exception:
                time_label = ""

            snippet = detail.get("snippet", "")[:100]

            emails.append({
                "subject": subject,
                "sender": sender,
                "time": time_label,
                "snippet": snippet,
                "account": account["name"],
            })

        return emails

    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.error("Gmail error for '%s': %s", account["name"], exc)
        return []


def get_gmail_summary(hours: int = 24) -> str:
    all_emails: list[dict] = []
    missing = []

    for account in ACCOUNTS:
        if not account["token"].exists():
            missing.append(account["name"])
            continue
        all_emails.extend(_fetch_emails_for_account(account, hours))

    if not all_emails:
        return f"אין מיילים שלא נקראו ב-{hours} השעות האחרונות."

    lines = [f"מיילים שלא נקראו ({len(all_emails)}):"]
    for em in all_emails:
        line = f"  • [{em['account']}] {em['time']} — {em['sender']}: {em['subject']}"
        if em["snippet"]:
            line += f"\n    {em['snippet']}"
        lines.append(line)

    return "\n".join(lines)
