"""TOBOR Telegram transport — outbound only.

Sends messages to the configured Telegram chat via Bot API.
No PTB dependency. No webhook. No polling. Fire-and-forget.
"""
import logging
import os

import httpx

log = logging.getLogger(__name__)

_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


async def send_message(text: str, parse_mode: str = "HTML") -> bool:
    """Send a message to the configured Telegram chat.

    Returns True on success, False on failure. Never raises.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        log.warning("Telegram not configured — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False

    url = _API_BASE.format(token=token)
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            log.info("Telegram: message sent (%d chars)", len(text))
            return True
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        # Retry once without parse_mode in case HTML caused the failure
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json={**payload, "parse_mode": None})
                response.raise_for_status()
                return True
        except Exception:
            return False
