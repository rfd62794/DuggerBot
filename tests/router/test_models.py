"""Tests for duggerbot.router.models — Phase 1."""

import pytest
from pydantic import ValidationError

from duggerbot.router.models import (
    TaskType,
    Provider,
    ProviderStatus,
    TaskRequest,
    RouteResult,
)


def test_task_type_values():
    """TaskType enum has RESEARCH, FAST_LOOKUP, LOCAL_INFERENCE, GENERAL."""
    assert TaskType.RESEARCH == "research"
    assert TaskType.FAST_LOOKUP == "fast_lookup"
    assert TaskType.LOCAL_INFERENCE == "local_inference"
    assert TaskType.GENERAL == "general"
    assert len(TaskType) == 4


def test_provider_valid():
    """Provider validates with required fields."""
    p = Provider(
        name="gemini",
        role="primary",
        models=["gemini-2.0-flash"],
        health_endpoint="https://example.com/health",
    )
    assert p.name == "gemini"
    assert p.role == "primary"
    assert p.models == ["gemini-2.0-flash"]


def test_provider_defaults():
    """enabled=True, cost=0.0, daily_cap_usd=None by default."""
    p = Provider(
        name="test",
        role="test",
        models=[],
        health_endpoint="https://example.com",
    )
    assert p.enabled is True
    assert p.cost_per_1k_tokens == 0.0
    assert p.daily_cap_usd is None
    assert p.keep_alive is None
    assert p.free_tier is None


def test_provider_status_defaults():
    """ProviderStatus.checked_at auto-populated."""
    status = ProviderStatus(name="gemini", available=True)
    assert status.checked_at is not None
    assert status.error is None
    assert status.latency_ms is None


def test_task_request_require_local_default():
    """require_local defaults to False."""
    req = TaskRequest(
        task_type=TaskType.GENERAL,
        prompt="test prompt",
    )
    assert req.require_local is False
    assert req.context_size == 0


def test_route_result_fallback_chain_default():
    """fallback_chain defaults to empty list."""
    result = RouteResult(
        provider="gemini",
        model="gemini-2.0-flash",
        task_type=TaskType.RESEARCH,
    )
    assert result.fallback_chain == []
    assert result.budget_remaining_usd == 0.0


def test_invalid_task_type():
    """ValidationError raised for unknown task_type string."""
    with pytest.raises(ValidationError):
        TaskRequest(
            task_type="nonexistent_type",
            prompt="test",
        )
