"""Tests for duggerbot.router.router — Phase 1."""

import httpx
import pytest
import yaml

from duggerbot.router.models import (
    TaskType,
    TaskRequest,
    ProviderExhaustedError,
)
from duggerbot.router.registry import ProviderRegistry
from duggerbot.router.health import HealthChecker
from duggerbot.router.router import ModelRouter


async def _make_router(
    providers_yaml,
    routing_yaml,
    handler,
    mock_http_client,
    ledger,
):
    """Helper to build a fully-wired ModelRouter for tests."""
    registry = ProviderRegistry(providers_yaml)
    registry.load()
    client = mock_http_client(handler)
    health = HealthChecker(client)
    with open(routing_yaml) as f:
        routing_config = yaml.safe_load(f)
    return ModelRouter(registry, health, ledger, routing_config)


async def test_routes_to_primary_when_healthy(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """Gemini healthy → RouteResult.provider == 'gemini'."""
    async def handler(request):
        return httpx.Response(200)

    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(task_type=TaskType.GENERAL, prompt="test")
    result = await router.route(request)
    assert result.provider == "gemini"
    assert result.task_type == TaskType.GENERAL


async def test_skips_unhealthy_falls_back(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """Gemini unhealthy, Groq healthy → routes to Groq."""
    call_count = 0

    async def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503)
        return httpx.Response(200)

    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(task_type=TaskType.GENERAL, prompt="test")
    result = await router.route(request)
    assert result.provider == "groq"


async def test_require_local_routes_to_ollama(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """require_local=True → attempts Ollama first."""
    async def handler(request):
        return httpx.Response(200)

    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(
        task_type=TaskType.GENERAL, prompt="test", require_local=True
    )
    result = await router.route(request)
    assert result.provider == "ollama"


async def test_provider_exhausted_raises(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """All providers unhealthy → ProviderExhaustedError."""
    async def handler(request):
        return httpx.Response(503)

    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(task_type=TaskType.GENERAL, prompt="test")
    with pytest.raises(ProviderExhaustedError):
        await router.route(request)


async def test_claude_budget_exceeded_skipped(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """Claude over cap → skipped in chain, exhausted if last."""
    async def handler(request):
        return httpx.Response(200)

    await ledger.record_call("claude", "claude-sonnet-4-6", cost_usd=0.30)
    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    result = await router.route(request)
    assert result.provider != "claude"


async def test_claude_routes_with_budget_remaining(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """Claude routes successfully and reports budget_remaining_usd."""
    call_count = 0

    async def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count <= 4:
            return httpx.Response(503)
        return httpx.Response(200)

    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(task_type=TaskType.GENERAL, prompt="test")
    result = await router.route(request)
    assert result.provider == "claude"
    assert result.budget_remaining_usd == 0.25


async def test_from_config(providers_yaml, routing_yaml, mock_http_client, ledger):
    """from_config classmethod creates a functional router."""
    async def handler(request):
        return httpx.Response(200)

    client = mock_http_client(handler)
    health = HealthChecker(client)
    router = ModelRouter.from_config(providers_yaml, routing_yaml, health, ledger)
    request = TaskRequest(task_type=TaskType.GENERAL, prompt="test")
    result = await router.route(request)
    assert result.provider == "gemini"


async def test_fallback_chain_recorded(
    providers_yaml, routing_yaml, mock_http_client, ledger
):
    """RouteResult.fallback_chain includes all tried providers."""
    call_count = 0

    async def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return httpx.Response(503)
        return httpx.Response(200)

    router = await _make_router(providers_yaml, routing_yaml, handler, mock_http_client, ledger)
    request = TaskRequest(task_type=TaskType.GENERAL, prompt="test")
    result = await router.route(request)
    assert len(result.fallback_chain) == 2
    assert "gemini" in result.fallback_chain
    assert "groq" in result.fallback_chain
