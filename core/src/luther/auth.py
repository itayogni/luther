"""
Central Google OAuth module.
All Google services share the same token files (one per account).
Adding new scopes here requires re-authorization (delete token_*.json and restart).
"""
import logging
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent.parent  # core/
CREDENTIALS_FILE = BASE_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

ACCOUNTS = [
    {"name": "עבודה", "token": BASE_DIR / "token_work.json"},
    {"name": "אישי",  "token": BASE_DIR / "token_personal.json"},
]


def get_credentials(token_path: Path) -> Credentials:
    """Load or refresh credentials from a token file. Runs OAuth flow if needed."""
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.error("Token refresh failed for %s: %s", token_path.name, exc)
                creds = None  # Force re-auth if refresh fails

        if not creds or not creds.valid:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(f"credentials.json not found at {CREDENTIALS_FILE}")

            # On headless server, don't attempt interactive OAuth — it will hang forever
            if os.environ.get("LUTHER_HEADLESS") == "1":
                raise RuntimeError(
                    f"Token expired for {token_path.name}. "
                    "Re-authenticate manually: run the app locally, then copy the token file to the server."
                )

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return creds


def get_connected_accounts() -> list[dict]:
    """Return only accounts that have a saved token."""
    return [a for a in ACCOUNTS if a["token"].exists()]
