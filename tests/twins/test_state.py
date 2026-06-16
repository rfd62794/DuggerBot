"""Tests for duggerbot.twins.state — Phase 3."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from duggerbot.twins.state import TwinStateReader
from duggerbot.twins.models import UsageSummary


def _make_reader(http_client=None, timeout_env=None, monkeypatch=None):
    if timeout_env and monkeypatch:
        monkeypatch.setenv("STATE_REQUEST_TIMEOUT_SECONDS", timeout_env)
    client = http_client or AsyncMock(spec=httpx.AsyncClient)
    return TwinStateReader(
        tower_host="100.106.80.49",
        mcp_port=8001,
        auth_token="test-token",
        http_client=client,
    )


async def test_get_usage_returns_summary_on_200():
    """200 response → UsageSummary."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"date": "2026-06-15", "providers": {}}
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=mock_resp)
    reader = _make_reader(http_client=client)
    result = await reader.get_usage()
    assert isinstance(result, UsageSummary)
    assert result.date == "2026-06-15"


async def test_get_usage_returns_none_on_timeout():
    """httpx timeout → None (no exception)."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    reader = _make_reader(http_client=client)
    result = await reader.get_usage()
    assert result is None


async def test_get_usage_returns_none_on_connection_error():
    """ConnectError → None."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
    reader = _make_reader(http_client=client)
    result = await reader.get_usage()
    assert result is None


async def test_get_usage_returns_none_on_401():
    """401 response → None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=mock_resp)
    reader = _make_reader(http_client=client)
    result = await reader.get_usage()
    assert result is None


async def test_get_provider_statuses_returns_dict_on_200():
    """200 → dict."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"gemini": {"available": True}}
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=mock_resp)
    reader = _make_reader(http_client=client)
    result = await reader.get_provider_statuses()
    assert isinstance(result, dict)
    assert "gemini" in result


async def test_get_provider_statuses_returns_none_on_timeout():
    """timeout → None."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    reader = _make_reader(http_client=client)
    result = await reader.get_provider_statuses()
    assert result is None


async def test_timeout_respects_env_var(monkeypatch):
    """STATE_REQUEST_TIMEOUT_SECONDS=1 used in client."""
    monkeypatch.setenv("STATE_REQUEST_TIMEOUT_SECONDS", "1")
    client = AsyncMock(spec=httpx.AsyncClient)
    reader = _make_reader(http_client=client)
    assert reader._timeout == 1.0


async def test_auth_header_sent():
    """Authorization: Bearer token in every request."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"date": "2026-06-15", "providers": {}}
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=mock_resp)
    reader = _make_reader(http_client=client)
    await reader.get_usage()
    call_kwargs = client.get.call_args
    assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-token"
