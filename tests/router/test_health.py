"""Tests for duggerbot.router.health — Phase 1."""

import httpx
import pytest

from duggerbot.router.models import Provider
from duggerbot.router.health import HealthChecker


def _make_provider(name: str = "test", endpoint: str = "https://example.com/health") -> Provider:
    return Provider(
        name=name,
        role="primary",
        models=["test-model"],
        health_endpoint=endpoint,
    )


async def test_healthy_provider_returns_available(mock_http_client):
    """200 response → ProviderStatus(available=True)."""
    async def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    client = mock_http_client(handler)
    checker = HealthChecker(client)
    status = await checker.check(_make_provider())
    assert status.available is True
    assert status.error is None
    assert status.latency_ms is not None


async def test_unhealthy_provider_returns_unavailable(mock_http_client):
    """503 response → ProviderStatus(available=False)."""
    async def handler(request):
        return httpx.Response(503)

    client = mock_http_client(handler)
    checker = HealthChecker(client)
    status = await checker.check(_make_provider())
    assert status.available is False
    assert "503" in status.error


async def test_timeout_returns_unavailable(mock_http_client):
    """httpx.TimeoutException → ProviderStatus(available=False)."""
    async def handler(request):
        raise httpx.TimeoutException("timed out")

    client = mock_http_client(handler)
    checker = HealthChecker(client)
    status = await checker.check(_make_provider())
    assert status.available is False
    assert "timed out" in status.error


async def test_connection_error_returns_unavailable(mock_http_client):
    """httpx.ConnectError → ProviderStatus(available=False)."""
    async def handler(request):
        raise httpx.ConnectError("connection refused")

    client = mock_http_client(handler)
    checker = HealthChecker(client)
    status = await checker.check(_make_provider())
    assert status.available is False
    assert "connection refused" in status.error


async def test_check_all_returns_all_providers(mock_http_client):
    """check_all with 3 providers returns dict with 3 keys."""
    async def handler(request):
        return httpx.Response(200)

    client = mock_http_client(handler)
    checker = HealthChecker(client)
    providers = [
        _make_provider("gemini", "https://a.com"),
        _make_provider("groq", "https://b.com"),
        _make_provider("ollama", "https://c.com"),
    ]
    results = await checker.check_all(providers)
    assert len(results) == 3
    assert all(s.available for s in results.values())


async def test_ollama_failure_does_not_raise(mock_http_client):
    """Ollama connection refused → status not exception."""
    async def handler(request):
        raise httpx.ConnectError("connection refused")

    client = mock_http_client(handler)
    checker = HealthChecker(client)
    ollama = Provider(
        name="ollama",
        role="local",
        models=["phi3.5:3.8b"],
        health_endpoint="http://localhost:11434/api/tags",
        keep_alive=-1,
    )
    status = await checker.check(ollama)
    assert status.available is False
    assert status.error is not None
    assert isinstance(status.name, str)
