"""Shared Google OAuth2 credential loader for TOBOR ponds."""
import os
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def get_credentials():
    """Load Google OAuth2 credentials from token file.

    Returns None if token file is missing or invalid.
    Callers should handle None gracefully.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        token_path = os.environ.get("GOOGLE_TOKEN_PATH", "config/google_token.json")

        if not Path(token_path).exists():
            log.warning("Google token not found at %s — run scripts/google_auth.py", token_path)
            return None

        creds = Credentials.from_authorized_user_file(token_path)

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(token_path, "w") as f:
                f.write(creds.to_json())
            log.info("Google credentials refreshed")

        return creds

    except Exception as e:
        log.error("Google credential load failed: %s", e)
        return None
