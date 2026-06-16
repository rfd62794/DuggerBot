# DuggerBot — Phase 3.8 Directive: Context Store + Cline Dispatch

*June 2026 | Lid-closed execution. Read fully before touching any file.*

---

> ⛔ **STOP:** Run `uv run pytest` before touching any file.
> Must report **206 passed, 0 failed, 0 skipped**.
> If count differs, stop and write the actual count to docs/decisions/pending.md — do not proceed.

---

## §0 Context

Phase 3.8 delivers two capabilities:

**1. Shared Context Store** — SQLite-backed key-value store accessible via MCP tools.
Claude writes directives, SDDs, and plans as context entries. Devin reads them.
TOBOR writes pond results. Claude reads them. No human transporting information.

**2. Cline Dispatch** — MCP tool that sends a bounded coding task to Cline CLI headless
with a specified Ollama model. Per ADR-010: dispatch is manual in Phase 3.8.
The tool is dumb — it takes a task string and a model, runs it, returns output.
Routing intelligence stays with Claude and Robert.

No RALPH. No pond schemas. No routing logic. Those are Phase 4.

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/context_store.py` | New | SQLite key-value store |
| `duggerbot/mcp/dev_tools.py` | Modify | Add 5 handlers |
| `duggerbot/mcp/tools.py` | Modify | Add 5 schemas |
| `tests/test_context_store.py` | New | 5 tests |
| `tests/mcp/test_dev_tools.py` | Modify | Add 5 tests for new handlers |
| `docs/state/current.md` | Modify | Update as final step |

**Read-only — do not touch:**
All of `duggerbot/router/`, all ADRs, `duggerbot/heartbeat.py`,
`duggerbot/providers/`, `duggerbot/twins/`, `duggerbot/mcp/auth.py`,
`duggerbot/version.py`, `duggerbot/main.py`, `SOUL.md`, `MEMORY.md`,
`HEARTBEAT.md`, all config YAMLs, `.clinerules`.

**Escalation rule (from .clinerules):**
If an architectural decision is required that this directive does not answer,
write the question to `docs/decisions/pending.md` and stop.
Do not guess. Do not pick autonomously.

---

## §2 Implementation

---

### 2.1 `duggerbot/context_store.py` (NEW)

SQLite-backed key-value store. One table. Async via aiosqlite.
DB file: `context.db` at repo root (gitignored).

Add `context.db` to `.gitignore`.

```python
"""Shared context store — SQLite key-value store for Claude↔Devin↔TOBOR coordination.

Claude writes: directives, SDDs, plans, pond results.
Devin reads: task context, full source references, architectural decisions.
TOBOR writes: pond outputs, health summaries.
Claude reads: pond results, completion proofs.
"""
import aiosqlite
from pathlib import Path

DB_PATH = Path("context.db")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS context (
    key      TEXT PRIMARY KEY,
    value    TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
)
"""

async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DB_PATH)
    await db.execute(_CREATE_TABLE)
    await db.commit()
    return db


async def write_context(key: str, value: str) -> None:
    """Write or overwrite a context entry."""
    async with await _get_db() as db:
        await db.execute(
            "INSERT INTO context (key, value, updated_at) VALUES (?, ?, datetime('now','utc')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value),
        )
        await db.commit()


async def read_context(key: str) -> str | None:
    """Read a context entry. Returns None if key does not exist."""
    async with await _get_db() as db:
        async with db.execute("SELECT value FROM context WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def delete_context(key: str) -> bool:
    """Delete a context entry. Returns True if key existed."""
    async with await _get_db() as db:
        cur = await db.execute("DELETE FROM context WHERE key = ?", (key,))
        await db.commit()
        return cur.rowcount > 0


async def list_context(prefix: str = "") -> list[str]:
    """List all keys, optionally filtered by prefix."""
    async with await _get_db() as db:
        async with db.execute(
            "SELECT key FROM context WHERE key LIKE ? ORDER BY key",
            (f"{prefix}%",),
        ) as cur:
            rows = await cur.fetchall()
            return [row[0] for row in rows]
```

> ⚠️ **RULE:** `context.db` is a runtime file — never committed.
> Add to `.gitignore` before running any tests.

> ⚠️ **RULE:** `_get_db()` creates the table on every call.
> This is intentional — idempotent, no migration needed.

---

### 2.2 `dispatch_to_cline` — Cline CLI headless execution

**Before writing any code:** Read the Cline CLI documentation.
Check: `cline --help` in a terminal on Nitro 5.
The exact flag syntax for headless task execution must be confirmed from the
actual installed version before implementation.

Expected pattern (verify before using):
```bash
cline task "<task string>" --model "ollama/<model_name>"
```

The handler:
- Takes `task: str` and `model: str`
- Runs Cline CLI as a subprocess (asyncio.create_subprocess_exec)
- Captures stdout and stderr
- Returns output as a string
- Times out after 300 seconds (configurable via CLINE_TIMEOUT_SECONDS env var)
- On timeout or error: returns error message string, does NOT raise

> ⚠️ **RULE:** asyncio.create_subprocess_exec only. Never shell=True.
> Never asyncio.create_subprocess_shell.

> ⚠️ **RULE:** Check Cline CLI flag syntax before writing the subprocess call.
> If `cline --help` is not available on the dev machine, write the question
> to docs/decisions/pending.md and stop.

---

### 2.3 `duggerbot/mcp/dev_tools.py` — add 5 handlers

Add imports at top:
```python
from duggerbot.context_store import write_context, read_context, delete_context, list_context
```

Add 5 handler functions following the exact pattern of existing handlers.
Each handler: validate input, call context_store or dispatch function, return dict.

| Handler | Input | Returns |
|---|---|---|
| `handle_write_context` | key: str, value: str | `{"key": key, "written": True}` |
| `handle_read_context` | key: str | `{"key": key, "value": str or None, "found": bool}` |
| `handle_delete_context` | key: str | `{"key": key, "deleted": bool}` |
| `handle_list_context` | prefix: str = "" | `{"keys": list[str], "count": int}` |
| `handle_dispatch_to_cline` | task: str, model: str | `{"output": str, "model": model, "success": bool}` |

---

### 2.4 `duggerbot/mcp/tools.py` — add 5 schemas

Add 5 tool schemas following the exact pattern of existing schemas.
Tool names:
- `write_context`
- `read_context`
- `delete_context`
- `list_context`
- `dispatch_to_cline`

Update the tool count assertion in tests after adding.

---

## §3 Test Anchors

Target: **10 new tests** (5 context store + 5 handler tests)
Full suite target: **216 passed, 0 failed, 0 skipped**

---

### `tests/test_context_store.py` — 5 tests

All tests use `tmp_path` fixture. Patch `duggerbot.context_store.DB_PATH`
to `tmp_path / "test_context.db"` in every test. Never write to real `context.db`.

| Test | Behaviour |
|---|---|
| `test_write_and_read_context` | Write key→value, read back same value |
| `test_read_returns_none_for_missing_key` | Read nonexistent key → None |
| `test_write_overwrites_existing_key` | Write key twice → second value wins |
| `test_delete_returns_true_when_key_exists` | Delete existing key → True, subsequent read → None |
| `test_list_context_filters_by_prefix` | Write "a:1", "a:2", "b:1" → list("a:") returns ["a:1","a:2"] |

### `tests/mcp/test_dev_tools.py` — 5 new tests

Mock `duggerbot.mcp.dev_tools.write_context` etc. — do not test SQLite in handler tests.

| Test | Behaviour |
|---|---|
| `test_handle_write_context_returns_written_true` | write_context mocked → handler returns `{"written": True}` |
| `test_handle_read_context_returns_value_when_found` | read_context returns "val" → handler returns `{"found": True, "value": "val"}` |
| `test_handle_read_context_returns_not_found` | read_context returns None → handler returns `{"found": False, "value": None}` |
| `test_handle_delete_context_returns_deleted_true` | delete_context returns True → handler returns `{"deleted": True}` |
| `test_handle_dispatch_to_cline_returns_output` | mock subprocess → handler returns `{"success": True, "output": "..."}` |

---

## §4 Completion Criteria

- [ ] `uv run pytest tests/test_context_store.py` — **5 passed, 0 failed**
- [ ] Full suite: **216 passed, 0 failed, 0 skipped**
- [ ] `context.db` in `.gitignore`
- [ ] `docs/decisions/pending.md` used for any escalation (do not guess)
- [ ] Cline CLI flag syntax confirmed before dispatch implementation
- [ ] `docs/state/current.md` updated
- [ ] No read-only files modified

**Proof required:**
```
uv run pytest --tb=no -q   (paste exact output line)
```

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 3.8 — Context Store + Cline Dispatch |
| Pre-flight | 206/0/0 |
| New tests | 10 |
| Full suite target | 216/0/0 |
| New files | `duggerbot/context_store.py`, `tests/test_context_store.py` |
| Modified files | `dev_tools.py`, `tools.py`, `.gitignore`, `state/current.md` |
| DB file | `context.db` — runtime, gitignored, never committed |
| Subprocess | asyncio.create_subprocess_exec only |
| Cline flags | Verify with `cline --help` before implementing |
| Escalation | Write to `docs/decisions/pending.md` and stop |
| Automated routing | Phase 4+ — not in this directive |
| Read-only | Everything not listed in §1 scope |
| Next phase | Phase 4 — RALPH + Ponds |
