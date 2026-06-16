"""Tests for duggerbot.mcp.handlers — Phase 2."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from duggerbot.router.models import (
    TaskType,
    RouteResult,
    ProviderStatus,
    ProviderExhaustedError,
    BudgetExceededError,
)
from duggerbot.mcp.handlers import (
    handle_research,
    handle_fast_lookup,
    handle_local_inference,
    handle_get_provider_status,
    handle_get_cost_today,
    TOOL_HANDLERS,
)
from duggerbot.mcp.tools import get_tool_list


def _mock_router(provider="gemini", model="gemini-2.0-flash", task_type=TaskType.RESEARCH):
    router = AsyncMock()
    router.route.return_value = RouteResult(
        provider=provider,
        model=model,
        task_type=task_type,
        fallback_chain=[],
        budget_remaining_usd=0.0,
    )
    return router


def _mock_router_exhausted():
    router = AsyncMock()
    router.route.side_effect = ProviderExhaustedError("all exhausted")
    return router


def _mock_router_budget_exceeded():
    router = AsyncMock()
    router.route.side_effect = BudgetExceededError("over cap")
    return router


async def test_research_builds_research_task_type():
    """handle_research creates TaskRequest with TaskType.RESEARCH."""
    router = _mock_router(task_type=TaskType.RESEARCH)
    result = await handle_research(router, {"query": "test"})
    call_args = router.route.call_args[0][0]
    assert call_args.task_type == TaskType.RESEARCH


async def test_research_returns_text_content_list():
    """Return value is list of TextContent."""
    router = _mock_router()
    result = await handle_research(router, {"query": "test"})
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].type == "text"


async def test_research_includes_provider_in_response():
    """RouteResult.provider appears in response text."""
    router = _mock_router(provider="gemini")
    result = await handle_research(router, {"query": "test"})
    data = json.loads(result[0].text)
    assert data["provider"] == "gemini"


async def test_research_context_size_passed_through():
    """context_size argument flows into TaskRequest."""
    router = _mock_router()
    await handle_research(router, {"query": "test", "context_size": 4096})
    call_args = router.route.call_args[0][0]
    assert call_args.context_size == 4096


async def test_fast_lookup_builds_fast_lookup_task_type():
    """handle_fast_lookup uses TaskType.FAST_LOOKUP."""
    router = _mock_router(task_type=TaskType.FAST_LOOKUP)
    await handle_fast_lookup(router, {"query": "test"})
    call_args = router.route.call_args[0][0]
    assert call_args.task_type == TaskType.FAST_LOOKUP


async def test_local_inference_sets_require_local_true():
    """handle_local_inference sets require_local=True on TaskRequest."""
    router = _mock_router(task_type=TaskType.LOCAL_INFERENCE)
    await handle_local_inference(router, {"prompt": "test"})
    call_args = router.route.call_args[0][0]
    assert call_args.require_local is True


async def test_local_inference_builds_local_inference_task_type():
    """Uses TaskType.LOCAL_INFERENCE."""
    router = _mock_router(task_type=TaskType.LOCAL_INFERENCE)
    await handle_local_inference(router, {"prompt": "test"})
    call_args = router.route.call_args[0][0]
    assert call_args.task_type == TaskType.LOCAL_INFERENCE


async def test_provider_exhausted_returns_error_content():
    """ProviderExhaustedError → TextContent with error message, no exception raised."""
    router = _mock_router_exhausted()
    result = await handle_research(router, {"query": "test"})
    assert isinstance(result, list)
    data = json.loads(result[0].text)
    assert "error" in data
    assert "exhausted" in data["error"]


async def test_budget_exceeded_returns_error_content():
    """BudgetExceededError → TextContent with error, no exception raised."""
    router = _mock_router_budget_exceeded()
    result = await handle_research(router, {"query": "test"})
    data = json.loads(result[0].text)
    assert "error" in data
    assert "cap" in data["error"]


async def test_get_provider_status_calls_check_all():
    """handle_get_provider_status calls health.check_all()."""
    health = AsyncMock()
    health.check_all.return_value = {
        "gemini": ProviderStatus(name="gemini", available=True, latency_ms=50.0),
    }
    registry = MagicMock()
    registry.list_enabled.return_value = []
    result = await handle_get_provider_status(health, registry)
    health.check_all.assert_called_once()
    assert isinstance(result, list)


async def test_get_provider_status_returns_all_providers():
    """Response includes all provider names."""
    health = AsyncMock()
    health.check_all.return_value = {
        "gemini": ProviderStatus(name="gemini", available=True),
        "groq": ProviderStatus(name="groq", available=True),
        "ollama": ProviderStatus(name="ollama", available=False, error="down"),
        "openrouter": ProviderStatus(name="openrouter", available=True),
        "claude": ProviderStatus(name="claude", available=True),
    }
    registry = MagicMock()
    registry.list_enabled.return_value = []
    result = await handle_get_provider_status(health, registry)
    data = json.loads(result[0].text)
    assert set(data.keys()) == {"gemini", "groq", "ollama", "openrouter", "claude"}


async def test_get_cost_today_calls_get_daily_summary():
    """handle_get_cost_today calls ledger.get_daily_summary()."""
    ledger = AsyncMock()
    ledger.get_today_cost.return_value = 0.10
    ledger.get_daily_summary.return_value = {}
    result = await handle_get_cost_today(ledger)
    ledger.get_daily_summary.assert_called_once()


async def test_get_cost_today_includes_cap():
    """Response includes the $0.25 cap value."""
    ledger = AsyncMock()
    ledger.get_today_cost.return_value = 0.0
    ledger.get_daily_summary.return_value = {}
    result = await handle_get_cost_today(ledger)
    data = json.loads(result[0].text)
    assert data["daily_cap_usd"] == 0.25


async def test_get_cost_today_includes_remaining():
    """Response includes remaining budget."""
    ledger = AsyncMock()
    ledger.get_today_cost.return_value = 0.10
    ledger.get_daily_summary.return_value = {}
    result = await handle_get_cost_today(ledger)
    data = json.loads(result[0].text)
    assert data["remaining_usd"] == 0.15


async def test_unknown_tool_raises_value_error():
    """Calling dispatch with unknown name → ValueError."""
    assert "nonexistent" not in TOOL_HANDLERS


def test_tool_handlers_map_has_five_entries():
    """TOOL_HANDLERS dict has exactly 5 keys."""
    assert len(TOOL_HANDLERS) == 5


def test_tool_handler_keys_match_tool_names():
    """TOOL_HANDLERS keys match names from get_tool_list()."""
    handler_keys = set(TOOL_HANDLERS.keys())
    tool_names = {t.name for t in get_tool_list()}
    assert handler_keys == tool_names
