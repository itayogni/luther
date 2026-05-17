import logging

from googleapiclient.discovery import build

from luther.auth import ACCOUNTS, get_credentials

logger = logging.getLogger(__name__)


def _fetch_tasks_for_account(account: dict) -> list[dict]:
    try:
        creds = get_credentials(account["token"])
        service = build("tasks", "v1", credentials=creds)

        # Get all task lists
        lists_result = service.tasklists().list(maxResults=10).execute()
        task_lists = lists_result.get("items", [])

        tasks = []
        for tl in task_lists:
            items = service.tasks().list(
                tasklist=tl["id"],
                showCompleted=False,
                showHidden=False,
                maxResults=20,
            ).execute().get("items", [])

            for item in items:
                if item.get("status") == "completed":
                    continue
                tasks.append({
                    "list": tl.get("title", ""),
                    "title": item.get("title", "(ללא שם)"),
                    "due": item.get("due", ""),
                    "notes": item.get("notes", ""),
                    "account": account["name"],
                })
        return tasks

    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.error("Tasks error for '%s': %s", account["name"], exc)
        return []


def create_task(
    title: str,
    notes: str = "",
    due_date: str = "",
    account_name: str = "אישי",
    task_list_name: str = "",
) -> str:
    """Create a new task. due_date in ISO format (e.g. 2026-05-18T00:00:00Z)."""
    account = next((a for a in ACCOUNTS if a["name"] == account_name), ACCOUNTS[-1])
    try:
        creds = get_credentials(account["token"])
        service = build("tasks", "v1", credentials=creds)

        # Find the target task list
        lists_result = service.tasklists().list(maxResults=10).execute()
        task_lists = lists_result.get("items", [])
        if not task_lists:
            return "שגיאה: לא נמצאו רשימות משימות."

        target_list = task_lists[0]  # default to first list
        if task_list_name:
            for tl in task_lists:
                if tl.get("title", "").lower() == task_list_name.lower():
                    target_list = tl
                    break

        task_body: dict = {"title": title}
        if notes:
            task_body["notes"] = notes
        if due_date:
            task_body["due"] = due_date

        service.tasks().insert(tasklist=target_list["id"], body=task_body).execute()
        result = f"נוצרה משימה: {title}"
        if due_date:
            result += f" (עד {_format_due(due_date).strip(' —')})"
        return result + f" (חשבון {account_name})"

    except Exception as exc:
        logger.error("Failed to create task: %s", exc)
        return f"שגיאה ביצירת משימה: {exc}"


def complete_task(title: str, account_name: str = "אישי") -> str:
    """Mark a task as completed by searching for its title."""
    account = next((a for a in ACCOUNTS if a["name"] == account_name), ACCOUNTS[-1])
    try:
        creds = get_credentials(account["token"])
        service = build("tasks", "v1", credentials=creds)

        lists_result = service.tasklists().list(maxResults=10).execute()
        for tl in lists_result.get("items", []):
            items = service.tasks().list(
                tasklist=tl["id"], showCompleted=False, maxResults=50,
            ).execute().get("items", [])
            for item in items:
                if title.lower() in item.get("title", "").lower():
                    item["status"] = "completed"
                    service.tasks().update(
                        tasklist=tl["id"], task=item["id"], body=item,
                    ).execute()
                    return f"משימה הושלמה: {item['title']}"

        return f"לא נמצאה משימה עם השם '{title}'."

    except Exception as exc:
        logger.error("Failed to complete task: %s", exc)
        return f"שגיאה בהשלמת משימה: {exc}"


def _format_due(due_str: str) -> str:
    if not due_str:
        return ""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
        return f" — עד {dt.day}/{dt.month}"
    except Exception:
        return ""


def get_tasks_summary() -> str:
    all_tasks: list[dict] = []
    missing = []

    for account in ACCOUNTS:
        if not account["token"].exists():
            missing.append(account["name"])
            continue
        all_tasks.extend(_fetch_tasks_for_account(account))

    if not all_tasks:
        return "אין משימות פתוחות." if not missing else ""

    lines = ["משימות פתוחות:"]
    # Group by list name
    by_list: dict[str, list] = {}
    for t in all_tasks:
        key = f"[{t['account']}] {t['list']}"
        by_list.setdefault(key, []).append(t)

    for list_name, tasks in by_list.items():
        lines.append(f"\n{list_name}:")
        for t in tasks:
            line = f"  • {t['title']}{_format_due(t['due'])}"
            if t["notes"]:
                line += f" ({t['notes'][:60]})"
            lines.append(line)

    return "\n".join(lines)
