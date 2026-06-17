"""One-time Google OAuth2 authorization.

Run this script once to authorize TOBOR's Google access.
Browser opens — sign in and allow all requested permissions.
Token saved to config/google_token.json.

Usage: uv run python scripts/google_auth.py
"""
import os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]


def main() -> None:
    secrets = os.environ.get("GOOGLE_CLIENT_SECRETS", "config/client_secret.json")
    token_path = os.environ.get("GOOGLE_TOKEN_PATH", "config/google_token.json")

    if not Path(secrets).exists():
        raise FileNotFoundError(
            f"client_secret.json not found at {secrets}. "
            "Copy it from PrivyBot: config/client_secret.json"
        )

    Path(token_path).parent.mkdir(parents=True, exist_ok=True)

    flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
    creds = flow.run_local_server(port=8080)

    with open(token_path, "w") as f:
        f.write(creds.to_json())

    print(f"✅ Auth complete. Token saved to {token_path}")
    print("You can now start TOBOR — credentials will load automatically.")


if __name__ == "__main__":
    main()
