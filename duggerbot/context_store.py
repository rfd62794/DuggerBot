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

async def _ensure_table(db: aiosqlite.Connection) -> None:
    await db.execute(_CREATE_TABLE)
    await db.commit()


async def write_context(key: str, value: str) -> None:
    """Write or overwrite a context entry."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        await db.execute(
            "INSERT INTO context (key, value, updated_at) VALUES (?, ?, datetime('now','utc')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value),
        )
        await db.commit()


async def read_context(key: str) -> str | None:
    """Read a context entry. Returns None if key does not exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        async with db.execute("SELECT value FROM context WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def delete_context(key: str) -> bool:
    """Delete a context entry. Returns True if key existed."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        cur = await db.execute("DELETE FROM context WHERE key = ?", (key,))
        await db.commit()
        return cur.rowcount > 0


async def list_context(prefix: str = "") -> list[str]:
    """List all keys, optionally filtered by prefix."""
    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_table(db)
        async with db.execute(
            "SELECT key FROM context WHERE key LIKE ? ORDER BY key",
            (f"{prefix}%",),
        ) as cur:
            rows = await cur.fetchall()
            return [row[0] for row in rows]
