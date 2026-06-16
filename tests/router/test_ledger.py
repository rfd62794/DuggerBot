"""Tests for duggerbot.router.ledger — Phase 1."""

from datetime import date, datetime, timezone
from unittest.mock import patch

import aiosqlite
import pytest

from duggerbot.router.models import BudgetExceededError
from duggerbot.router.ledger import UsageLedger


async def test_initialize_creates_table(tmp_path):
    """initialize() runs without error, table exists."""
    db_path = tmp_path / "test.db"
    ledger = UsageLedger(db_path)
    await ledger.initialize()
    async with aiosqlite.connect(str(db_path)) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_usage'"
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "api_usage"


async def test_get_today_cost_empty(ledger):
    """Returns 0.0 for provider with no records today."""
    cost = await ledger.get_today_cost("claude")
    assert cost == 0.0


async def test_record_and_retrieve_cost(ledger):
    """record_call() then get_today_cost() returns correct sum."""
    await ledger.record_call("claude", "claude-sonnet-4-6", cost_usd=0.05)
    await ledger.record_call("claude", "claude-sonnet-4-6", cost_usd=0.03)
    cost = await ledger.get_today_cost("claude")
    assert abs(cost - 0.08) < 1e-9


async def test_multiple_providers_tracked_independently(ledger):
    """Claude cost does not affect Gemini cost."""
    await ledger.record_call("claude", "claude-sonnet-4-6", cost_usd=0.10)
    await ledger.record_call("gemini", "gemini-2.0-flash", cost_usd=0.00)
    claude_cost = await ledger.get_today_cost("claude")
    gemini_cost = await ledger.get_today_cost("gemini")
    assert abs(claude_cost - 0.10) < 1e-9
    assert gemini_cost == 0.0


async def test_check_budget_within_cap(ledger):
    """No exception when today_cost + estimated < cap."""
    await ledger.record_call("claude", "claude-sonnet-4-6", cost_usd=0.10)
    await ledger.check_budget("claude", daily_cap_usd=0.25, estimated_cost=0.10)


async def test_check_budget_exceeds_cap(ledger):
    """BudgetExceededError when today_cost + estimated > cap."""
    await ledger.record_call("claude", "claude-sonnet-4-6", cost_usd=0.20)
    with pytest.raises(BudgetExceededError):
        await ledger.check_budget("claude", daily_cap_usd=0.25, estimated_cost=0.10)


async def test_daily_rollover(ledger):
    """Record with yesterday's date does not count toward today's cap."""
    yesterday = "2020-01-01"
    async with aiosqlite.connect(str(ledger._db_path)) as db:
        await db.execute(
            "INSERT INTO api_usage (provider, model, tokens_in, tokens_out, cost_usd, called_at, date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("claude", "claude-sonnet-4-6", 100, 50, 0.20, "2020-01-01T12:00:00", yesterday),
        )
        await db.commit()
    cost = await ledger.get_today_cost("claude")
    assert cost == 0.0
    await ledger.check_budget("claude", daily_cap_usd=0.25, estimated_cost=0.10)
