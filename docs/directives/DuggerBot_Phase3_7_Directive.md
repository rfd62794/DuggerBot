# DuggerBot — Phase 3.7 Directive: Deployment Gate

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run `uv run pytest` before touching any file.
> Must report **195 passed, 0 failed, 0 skipped** (Phase 3.6 certified floor).
> If count differs, stop and report — do not proceed.

---

## §0 Context

Phase 3.6 delivered version tracking and self-update — certified at 195/0/0.

Phase 3.7 is the **deployment gate**. The only code deliverable is `main.py` —
the entry point NSSM runs. Without it, the service cannot start. Everything else
in this phase is manual configuration and live verification that the tether works
end to end.

This phase is a gate, not a build. Thirty minutes if nothing goes wrong. The
reason it exists as its own phase: deployment problems must be isolated from
Phase 4 RALPH code. You do not debug NSSM plumbing while a research loop is
in flight.

**What Phase 3.7 produces:**
- `duggerbot/main.py` — entry point with logging and env loading
- `logs/.gitkeep` — ensures `logs/` exists in the repo
- `tests/test_main.py` — 4 tests
- Confirmed live tether: Claude and Windsurf both hitting real DuggerBot

**What Phase 3.7 does NOT produce:**
- Any RALPH code
- Changes to existing modules
- New MCP tools
- Changes to the twin protocol

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/main.py` | New | Entry point — logging, env load, uvicorn start |
| `logs/.gitkeep` | New | Ensures logs/ directory exists in repo |
| `tests/test_main.py` | New | 4 tests |
| `docs/state/current.md` | Modify | Update as final code step |

**Everything else is read-only. No exceptions.**

All `duggerbot/` modules, all test files, all config files, all ADRs, all scripts —
read-only. The only code written in Phase 3.7 is `main.py` and its test file.

---

## §2 Implementation

---

### 2.1 `logs/.gitkeep`

Create an empty file at `logs/.gitkeep`. This commits the `logs/` directory to
the repo so NSSM has somewhere to write stdout/stderr on a fresh clone.

Add `logs/*.log` to `.gitignore` so log files are never committed.

---

### 2.2 `duggerbot/main.py` (NEW)

Three design constraints from the directive — all three are required:

> ⚠️ **RULE:** `load_dotenv(".env.local", override=False)` — system environment
> variables win over the file. NSSM may set `INSTANCE_ROLE` at the service level.
> If `override=True` is used, the file silently overwrites NSSM's service-level
> env vars. This is wrong. Use `override=False`.

> ⚠️ **RULE:** `logging.basicConfig` with two handlers: `StreamHandler` (NSSM
> captures this as stdout) and `FileHandler("logs/duggerbot.log")` (second audit
> trail that survives NSSM log rotation). One `basicConfig` call. No logging
> framework. No third-party log libraries.

> ⚠️ **RULE:** `uvicorn.run()` takes the app as an import string
> `"duggerbot.mcp.server:app"`, not as the imported object. This allows uvicorn
> to handle module reloading correctly if ever needed.

```python
"""DuggerBot — entry point.

Run via:  uv run python -m duggerbot.main
NSSM:     uv run python -m duggerbot.main (in AppDirectory = repo root)
"""
import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv


def _configure_logging() -> None:
    """Configure root logger with console and file handlers.

    StreamHandler: captured by NSSM as stdout/stderr.
    FileHandler:   secondary audit trail in logs/duggerbot.log,
                   survives NSSM log rotation.
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "duggerbot.log"),
        ],
    )


def main() -> None:
    # override=False: system env vars (e.g. set by NSSM) win over .env.local
    load_dotenv(".env.local", override=False)
    _configure_logging()

    log = logging.getLogger(__name__)
    port = int(os.environ.get("MCP_PORT", "8001"))
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    instance = os.environ.get("INSTANCE_ROLE", "unknown")

    log.info("TOBOR starting — instance=%s host=%s port=%s", instance, host, port)

    uvicorn.run(
        "duggerbot.mcp.server:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
```

---

## §3 Test Anchors

Mock `load_dotenv`, `uvicorn.run`, and `logging.basicConfig` in all tests.
Do not create real files, real log handlers, or start real servers.

Target: **4 new tests**
Full suite target: **199 passed, 0 failed, 0 skipped**

---

### `tests/test_main.py` — 4 tests

| Test | Behaviour |
|---|---|
| `test_load_dotenv_called_with_override_false` | `load_dotenv` called with `.env.local` and `override=False` — not True |
| `test_uvicorn_run_uses_MCP_PORT_env` | `MCP_PORT=9000` in env → uvicorn called with `port=9000` |
| `test_uvicorn_run_defaults_port_8001` | No `MCP_PORT` → uvicorn called with `port=8001` |
| `test_logging_configured_with_stream_and_file_handler` | `basicConfig` called with handlers containing both `StreamHandler` and `FileHandler` |

Mock pattern:
```python
# In each test, patch before calling main():
mocker.patch("duggerbot.main.load_dotenv")
mocker.patch("duggerbot.main.uvicorn.run")
mocker.patch("duggerbot.main.logging.basicConfig")
mocker.patch("duggerbot.main.logging.FileHandler", return_value=MagicMock())
```

---

## §4 Completion Criteria — Two Parts

### Part A: Code (Devin executes)

- [ ] `uv run pytest tests/test_main.py` reports **4 passed, 0 failed, 0 skipped**
- [ ] Full suite: **199 passed, 0 failed, 0 skipped**
- [ ] `main.py` uses `override=False` in `load_dotenv` — confirm by reading file
- [ ] `main.py` uses two handlers in `basicConfig` — confirm by reading file
- [ ] `main.py` uses import string `"duggerbot.mcp.server:app"` in `uvicorn.run` — confirm
- [ ] `logs/.gitkeep` exists, `logs/*.log` added to `.gitignore`
- [ ] `docs/state/current.md` updated

### Part B: Manual Deployment Verification (Robert executes)

Each item below is a distinct failure mode. All four must pass before Phase 4 begins.

- [ ] **NSSM service starts cleanly**
  - Configure NSSM with ADR-009 prescriptive settings (see `scripts/initialize.ps1`)
  - `nssm start DuggerBot`
  - `curl http://localhost:8001/health` returns `{"status": "ok", "version": "0.1.0.rN", ...}`
  - `logs/duggerbot.log` exists and contains startup message

- [ ] **Claude Desktop tether confirmed**
  - Claude Desktop MCP config: add DuggerBot SSE endpoint at `http://localhost:8001/sse`
  - Auth: `MCP_AUTH_TOKEN` value from `.env.local`
  - Call `get_version()` from Claude Desktop — receives real output with live revision number
  - Output includes `instance_role: "development"` (confirms Nitro 5, not Tower)

- [ ] **Windsurf tether confirmed**
  - Windsurf MCP config: same endpoint, `DEVIN_AUTH_TOKEN` from `.env.local`
  - Call `get_version()` from Windsurf — receives real output
  - Different auth token than Claude Desktop — confirms CallerIdentity distinction is live

- [ ] **Tether verification call**
  - From Claude Desktop (not Robert pasting), call `verify_test_floor()`
  - Returns `{"passed": 199, "failed": 0, "skipped": 0, "floor_met": true}`
  - This confirms DuggerBot is running against the real repo on Nitro 5

**Phase 4 does not start until all four manual checks pass.**

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 3.7 — Deployment Gate |
| Pre-flight | 195/0/0 (Phase 3.6 certified) |
| New tests | 4 |
| Full suite target | 199/0/0 |
| New files | `duggerbot/main.py`, `logs/.gitkeep`, `tests/test_main.py` |
| `.gitignore` addition | `logs/*.log` |
| `load_dotenv` | `override=False` — mandatory, system env wins |
| Logging | `basicConfig` with StreamHandler + FileHandler — no frameworks |
| uvicorn app arg | Import string, not object: `"duggerbot.mcp.server:app"` |
| NSSM config | Follow `scripts/initialize.ps1` or ADR-009 — prescriptive, not advisory |
| Tether gate | All 4 manual checks must pass before Phase 4 |
| Read-only | Everything except the 3 new files and .gitignore |
| Next phase | Phase 4 — RALPH Rebuilt (only after Part B clears) |
