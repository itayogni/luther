"""Run this once to authorize Google accounts with all required scopes."""
from luther.auth import ACCOUNTS, get_credentials

for account in ACCOUNTS:
    if not account["token"].exists():
        print(f"\nAuthorizing account: {account['name']}")
        print("A browser window will open — sign in with the correct Google account.\n")
        try:
            get_credentials(account["token"])
            print(f"Account '{account['name']}' authorized successfully.")
        except Exception as e:
            print(f"Failed: {e}")
    else:
        print(f"Account '{account['name']}' already has a token — skipping.")
        print("(Delete the token file to re-authorize with new scopes.)")

print("\nDone.")
