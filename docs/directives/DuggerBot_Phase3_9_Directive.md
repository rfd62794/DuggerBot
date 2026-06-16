# DuggerBot — Phase 3.9 Directive: HEARTBEAT Reader

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run `uv run pytest` before touching any file.
> Must report **200 passed, 0 failed, 0 skipped**.
> If count differs, stop and report — do not proceed.

---

## §0 Context

Phase 3.9 adds one background coroutine: the HEARTBEAT reader.

Robert writes a research task to `HEARTBEAT.md` before sleep. TOBOR checks
it on a configurable interval. If content is present, it routes to the
provider router (Gemini Flash primary), writes the response to
`docs/heartbeat_response.md` with a timestamp, and clears `HEARTBEAT.md`.

This is the first real production use of the provider router. If there is
a credential issue, a timeout, or a routing failure in Gemini Flash, it
surfaces here — in 30 lines — not buried inside Phase 4's RALPH complexity.

**What Phase 3.9 is not:**
- Not RALPH. No research loop, no pond schemas, no morning dispatch.
- Not a new MCP tool. No tool schema changes.
- Not pond schemas. Those are Phase 4 scope.

One coroutine. One file read. One router call. One file write.

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/heartbeat.py` | New | Heartbeat coroutine — read, route, write, clear |
| `tests/test_heartbeat.py` | New | 4 tests |
| `HEARTBEAT.md` | New | Empty committed file — TOBOR's inbox |
| `duggerbot/mcp/server.py` | Modify | Start heartbeat_loop in lifespan alongside update check |
| `tests/mcp/test_server.py` | Modify | Account for second background task in lifespan test |
| `docs/state/current.md` | Modify | Update as final step |
| `.gitignore` | Modify | Add `docs/heartbeat_response.md` — runtime output, not committed |

**Read-only — do not touch:**
All of `duggerbot/router/`, all ADRs, all config YAMLs, `SOUL.md`,
`MEMORY.md`, `AGENTS.md`, `duggerbot/twins/`, `duggerbot/mcp/auth.py`,
`duggerbot/mcp/tools.py`, `duggerbot/mcp/handlers.py`.

---

## §2 Implementation

---

### 2.1 `HEARTBEAT.md` (empty committed file)

Create an empty `HEARTBEAT.md` at the repo root. This is TOBOR's inbox.
Robert writes tasks here. TOBOR clears it after processing.

---

### 2.2 `duggerbot/heartbeat.py` (NEW)

```python
"""HEARTBEAT reader — TOBOR's overnight task inbox.

Background coroutine that checks HEARTBEAT.md on a configurable interval.
If content is present: route to provider router, write response, clear inbox.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

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


async def heartbeat_loop(router) -> None:
    """Background coroutine: check HEARTBEAT.md, route, respond, clear.

    Args:
        router: Provider router instance from app.state.
                Must implement async route(prompt: str) -> str.
    """
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
            response = await router.route(prompt=task)
            _write_response(task, response)
            _clear_heartbeat()
            log.info("Heartbeat task processed and cleared")
        except Exception:
            log.exception("Heartbeat loop error — continuing")
```

> ⚠️ **RULE:** `router.route()` is async — always `await` it.
> Look at `tests/router/test_router.py` to confirm the exact method
> signature before writing the call. Match what exists — do not invent.

> ⚠️ **RULE:** All file I/O in `heartbeat.py` is synchronous (`Path.read_text`,
> `Path.write_text`). Do not use `aiofiles`. The files are small; sync I/O
> is correct and simpler here.

> ⚠️ **RULE:** `HEARTBEAT_INTERVAL_SECONDS` env var overrides the default.
> Robert will set it to `120` (2 minutes) in `.env.local` tonight for
> testing, then remove it to revert to 30 minutes. The directive must
> support this without code changes.

---

### 2.3 `duggerbot/mcp/server.py` — add heartbeat_loop to lifespan

The lifespan already starts the update check loop. Add heartbeat_loop
alongside it using the same pattern.

> ⚠️ **RULE:** Read the current lifespan implementation before editing.
> Match the existing pattern exactly — do not restructure the lifespan.
> The update check loop is already there; add heartbeat_loop alongside it.

The router instance is available from `app.state` in the lifespan context.
Pass it to `heartbeat_loop`. Import `heartbeat_loop` from `duggerbot.heartbeat`.

---

## §3 Test Anchors

Target: **4 new tests** in `tests/test_heartbeat.py`
Full suite target: **204 passed, 0 failed, 0 skipped**

All tests use `tmp_path` to avoid touching the real `HEARTBEAT.md`.
Patch `duggerbot.heartbeat.HEARTBEAT_PATH` and `duggerbot.heartbeat.RESPONSE_PATH`
to point to `tmp_path` locations in every test.

Do not test `heartbeat_loop` as an async loop — test the helper functions
in isolation and mock the router for the integration path.

---

### `tests/test_heartbeat.py` — 4 tests

| Test | Behaviour |
|---|---|
| `test_read_heartbeat_returns_none_when_empty` | HEARTBEAT.md exists but is empty → `_read_heartbeat()` returns None |
| `test_read_heartbeat_returns_content_when_present` | HEARTBEAT.md contains a task → `_read_heartbeat()` returns stripped content |
| `test_write_response_creates_file_with_task_and_response` | `_write_response("task", "answer")` → response file contains both strings and a timestamp |
| `test_clear_heartbeat_empties_file` | `_clear_heartbeat()` → HEARTBEAT.md is empty string after call |

---

### `tests/mcp/test_server.py` — update only

The lifespan test that asserts background tasks are started needs to account
for the second task (heartbeat_loop). Update the count assertion only.
Do not add new server tests.

---

## §4 Completion Criteria

### Part A — Code (Devin executes)

- [ ] `uv run pytest tests/test_heartbeat.py` reports **4 passed, 0 failed, 0 skipped**
- [ ] Full suite: **204 passed, 0 failed, 0 skipped**
- [ ] `heartbeat.py` uses synchronous file I/O — no aiofiles
- [ ] `heartbeat.py` reads interval from `HEARTBEAT_INTERVAL_SECONDS` env var
- [ ] `HEARTBEAT.md` committed empty at repo root
- [ ] `docs/heartbeat_response.md` added to `.gitignore`
- [ ] `docs/state/current.md` updated
- [ ] No read-only files modified

### Part B — Manual Verification (Robert executes)

Set `HEARTBEAT_INTERVAL_SECONDS=120` in `.env.local`, restart NSSM,
then:

- [ ] Write a real research task to `HEARTBEAT.md` (2–3 sentences is enough)
- [ ] Wait 2 minutes
- [ ] `docs/heartbeat_response.md` exists with response and timestamp
- [ ] `HEARTBEAT.md` is empty
- [ ] `logs/duggerbot.log` shows "Heartbeat task received" and "processed and cleared"

All five must pass before Phase 4 begins.
After verification: remove `HEARTBEAT_INTERVAL_SECONDS` from `.env.local`,
restart NSSM to restore 30-minute default.

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 3.9 — HEARTBEAT Reader |
| Pre-flight | 200/0/0 |
| New tests | 4 |
| Full suite target | 204/0/0 |
| New files | `duggerbot/heartbeat.py`, `tests/test_heartbeat.py`, `HEARTBEAT.md` |
| Modified files | `server.py` (lifespan), `test_server.py` (count), `.gitignore`, `state/current.md` |
| Read-only | Everything else |
| Router call | `await router.route(prompt=task)` — verify signature in test_router.py first |
| File I/O | Synchronous — no aiofiles |
| Interval default | 1800s (30 min) — override via `HEARTBEAT_INTERVAL_SECONDS` |
| Tonight's test | Set `HEARTBEAT_INTERVAL_SECONDS=120`, write task, wait 2 min |
| Phase 4 dependency | This phase must be certified before Phase 4 begins |
| Pond schemas | Phase 4 scope — do not add here |
