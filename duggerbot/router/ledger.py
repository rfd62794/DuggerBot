"""Track usage per provider per day in SQLite and enforce the Claude API $0.25/day cap."""

from datetime import date, datetime, timezone
from pathlib import Path

import aiosqlite

from duggerbot.router.models import BudgetExceededError


SCHEMA = """
CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    called_at TEXT NOT NULL,
    date TEXT NOT NULL
);
"""


class UsageLedger:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        """Create tables if not exist. Call once at startup."""
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def record_call(
        self,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Write one usage record. date field is today's date."""
        now = datetime.now(timezone.utc)
        today = date.today().isoformat()
        async with aiosqlite.connect(str(self._db_path)) as db:
            await db.execute(
                "INSERT INTO api_usage (provider, model, tokens_in, tokens_out, cost_usd, called_at, date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (provider, model, tokens_in, tokens_out, cost_usd, now.isoformat(), today),
            )
            await db.commit()

    async def get_today_cost(self, provider: str) -> float:
        """Return sum of cost_usd for provider on today's date."""
        today = date.today().isoformat()
        async with aiosqlite.connect(str(self._db_path)) as db:
            cursor = await db.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) FROM api_usage WHERE provider = ? AND date = ?",
                (provider, today),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0.0

    async def check_budget(
        self, provider: str, daily_cap_usd: float, estimated_cost: float
    ) -> None:
        """Raise BudgetExceededError if today_cost + estimated_cost > cap."""
        today_cost = await self.get_today_cost(provider)
        if today_cost + estimated_cost > daily_cap_usd:
            raise BudgetExceededError(
                f"{provider} daily cap ${daily_cap_usd:.2f} would be exceeded: "
                f"${today_cost:.4f} spent + ${estimated_cost:.4f} estimated"
            )

    async def get_daily_summary(self) -> dict[str, dict]:
        """Return {provider: {calls, tokens_in, tokens_out, cost_usd}} for today."""
        today = date.today().isoformat()
        async with aiosqlite.connect(str(self._db_path)) as db:
            cursor = await db.execute(
                "SELECT provider, COUNT(*), SUM(tokens_in), SUM(tokens_out), SUM(cost_usd) "
                "FROM api_usage WHERE date = ? GROUP BY provider",
                (today,),
            )
            rows = await cursor.fetchall()
            return {
                row[0]: {
                    "calls": row[1],
                    "tokens_in": row[2],
                    "tokens_out": row[3],
                    "cost_usd": row[4],
                }
                for row in rows
            }
