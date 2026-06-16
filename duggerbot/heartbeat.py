"""HEARTBEAT reader — TOBOR's overnight task inbox.

Background coroutine that checks HEARTBEAT.md on a configurable interval.
If content is present: call Gemini Flash, write response, clear inbox.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from duggerbot.providers.gemini import call_gemini_flash
from duggerbot.providers.openrouter import call_openrouter

log = logging.getLogger(__name__)

HEARTBEAT_PATH = Path("HEARTBEAT.md")
RESPONSE_PATH = Path("docs/heartbeat_response.md")
DEFAULT_INTERVAL = 1800  # 30 minutes — override via HEARTBEAT_INTERVAL_SECONDS


def _get_interval() -> int:
    """Return check interval in seconds. Configurable for testing."""
    return int(os.environ.get("HEARTBEAT_INTERVAL_SECONDS", str(DEFAULT_INTERVAL)))


def _read_heartbeat() -> str | None:
    """Return stripped content if HEARTBEAT.md has a task, None if empty."""
    if not HEARTBEAT_PATH.exists():
        return None
    content = HEARTBEAT_PATH.read_text(encoding="utf-8").strip()
    return content if content else None


def _write_response(task: str, response: str) -> None:
    """Write response with timestamp to docs/heartbeat_response.md."""
    RESPONSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    output = (
        f"# Heartbeat Response\n\n"
        f"**Task:** {task}\n\n"
        f"**Processed:** {timestamp}\n\n"
        f"---\n\n"
        f"{response}\n"
    )
    RESPONSE_PATH.write_text(output, encoding="utf-8")


def _clear_heartbeat() -> None:
    """Clear HEARTBEAT.md after successful processing."""
    HEARTBEAT_PATH.write_text("", encoding="utf-8")


async def _call_provider(task: str) -> str:
    """Try Gemini first, fall back to OpenRouter on 429."""
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            return await call_gemini_flash(prompt=task, api_key=gemini_key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                log.warning("Gemini 429 — falling back to OpenRouter")
            else:
                raise

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        return await call_openrouter(prompt=task, api_key=openrouter_key)

    raise RuntimeError("No provider available — both GEMINI_API_KEY and OPENROUTER_API_KEY missing or 429")


async def heartbeat_loop() -> None:
    """Background coroutine: check HEARTBEAT.md, call provider, respond, clear."""
    interval = _get_interval()
    log.info("Heartbeat loop started — interval=%ds", interval)
    while True:
        await asyncio.sleep(interval)
        try:
            task = _read_heartbeat()
            if task is None:
                log.debug("Heartbeat: no task found")
                continue
            log.info("Heartbeat task received (%d chars)", len(task))
            response = await _call_provider(task)
            _write_response(task, response)
            _clear_heartbeat()
            log.info("Heartbeat task processed and cleared")
        except Exception:
            log.exception("Heartbeat loop error — continuing")
