"""HEARTBEAT reader — TOBOR's overnight task inbox.

Background coroutine that checks HEARTBEAT.md on a configurable interval.
If content is present: call Gemini Flash, write response, clear inbox.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from duggerbot.providers.gemini import call_gemini_flash
from duggerbot.providers.openrouter import call_openrouter
from duggerbot.telegram import send_message
from duggerbot.ponds.self_status import run as self_status_run

log = logging.getLogger(__name__)

HEARTBEAT_PATH = Path("HEARTBEAT.md")
RESPONSE_PATH = Path("docs/heartbeat_response.md")
DEFAULT_INTERVAL = 1800  # 30 minutes — override via HEARTBEAT_INTERVAL_SECONDS

# Reactive pacing intervals
FAST_INTERVAL = 5 * 60      # 5 min — just processed something
NORMAL_INTERVAL = 30 * 60   # 30 min — default idle
SLOW_INTERVAL = 60 * 60     # 60 min — nothing found 3+ times

# Module-level state for pond rotation and reactive pacing
_consecutive_empty: int = 0
_pond_index: int = 0

POND_ROTATION = [self_status_run]  # Phase 4b adds more

HEARTBEAT_SYSTEM = (
    "You are TOBOR's research assistant. Process the task thoroughly. "
    "You MUST end your response with this exact line:\n"
    "<!-- NEXT: [one sentence describing the logical follow-up task] -->\n"
    "This line is mandatory. The loop stops without it."
)


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
    with open(RESPONSE_PATH, "a", encoding="utf-8") as f:
        f.write(output)


def _append_to_response(source: str, content: str) -> None:
    """Append pond output or other content to heartbeat_response.md."""
    RESPONSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    output = (
        f"\n\n## {source} — {timestamp}\n\n"
        f"{content}\n"
    )
    with open(RESPONSE_PATH, "a", encoding="utf-8") as f:
        f.write(output)


def _clear_heartbeat() -> None:
    """Clear HEARTBEAT.md after successful processing."""
    HEARTBEAT_PATH.write_text("", encoding="utf-8")


def _extract_next_task(response: str) -> str | None:
    """Extract next task from <!-- NEXT: ... --> marker in response."""
    match = re.search(r'<!--\s*NEXT:\s*(.*?)\s*-->', response, re.DOTALL)
    return match.group(1).strip() if match else None


async def _call_provider(task: str) -> str:
    """Try Gemini first, fall back to OpenRouter on 429.

    Prepends system prompt requiring NEXT marker.
    """
    # Wrap task with system prompt
    wrapped_task = f"{HEARTBEAT_SYSTEM}\n\n---\n\n{task}"

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            return await call_gemini_flash(prompt=wrapped_task, api_key=gemini_key)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                log.warning("Gemini 429 — falling back to OpenRouter")
            else:
                raise

    openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
    if openrouter_key:
        return await call_openrouter(prompt=wrapped_task, api_key=openrouter_key)

    raise RuntimeError("No provider available — both GEMINI_API_KEY and OPENROUTER_API_KEY missing or 429")


def _get_sleep_interval(consecutive_empty: int) -> int:
    """Return sleep interval. Env var sets base; reactive pacing scales it.

    consecutive_empty == 0: min(FAST_INTERVAL, base) — just did work
    consecutive_empty 1-2:  base — normal idle
    consecutive_empty >= 3: min(SLOW_INTERVAL, base * 2) — backing off
    """
    base = _get_interval()  # reads HEARTBEAT_INTERVAL_SECONDS env var
    if consecutive_empty == 0:
        return min(FAST_INTERVAL, base)
    elif consecutive_empty >= 3:
        return min(SLOW_INTERVAL, base * 2)
    else:
        return base


async def heartbeat_loop() -> None:
    """Background coroutine: check HEARTBEAT.md, call provider, respond, clear.

    Reactive pacing: FAST after task/pond, NORMAL idle, SLOW after 3+ empty.
    """
    global _consecutive_empty, _pond_index

    interval = _get_interval()
    log.info("Heartbeat loop started — interval=%ds (reactive pacing active)", interval)
    while True:
        sleep_interval = _get_sleep_interval(_consecutive_empty)
        await asyncio.sleep(sleep_interval)
        try:
            task = _read_heartbeat()
            if task is None:
                # Run next pond in rotation
                pond_fn = POND_ROTATION[_pond_index % len(POND_ROTATION)]
                _pond_index += 1
                result = await pond_fn()
                summary = result.get("summary", str(result))
                _append_to_response(pond_fn.__name__, summary)
                await send_message(summary)
                log.info("Heartbeat: pond %s ran, Telegram sent (%d chars)",
                         pond_fn.__name__, len(summary))
                _consecutive_empty = 0  # Reset counter after pond run
                continue

            # Process inbox task
            _consecutive_empty = 0  # Reset counter
            log.info("Heartbeat task received (%d chars)", len(task))
            response = await _call_provider(task)
            _write_response(task, response)
            next_task = _extract_next_task(response)
            if next_task:
                HEARTBEAT_PATH.write_text(next_task, encoding="utf-8")
                log.info("Heartbeat: next task loaded (%d chars)", len(next_task))
            else:
                _clear_heartbeat()
            log.info("Heartbeat task processed")
        except Exception:
            log.exception("Heartbeat loop error — continuing")
            _consecutive_empty += 1
