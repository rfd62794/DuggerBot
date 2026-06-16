"""Tests for duggerbot.twins.coordinator — Phase 3."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock

from duggerbot.twins.coordinator import TwinCoordinator
from duggerbot.twins.identity import TwinIdentity
from duggerbot.twins.models import (
    DelegationRequest,
    DelegationResponse,
    InstanceRole,
    ProviderUsageRecord,
    UsageSummary,
)
from duggerbot.twins.presence import PresenceTracker
from duggerbot.twins.state import TwinStateReader
from duggerbot.router.models import TaskRequest, TaskType


def _make_identity(role: str, monkeypatch):
    monkeypatch.setenv("INSTANCE_ROLE", role)
    return TwinIdentity()


def _make_coordinator(
    identity,
    state_reader=None,
    presence=None,
    http_client=None,
):
    return TwinCoordinator(
        identity=identity,
        state_reader=state_reader,
        presence=presence,
        http_client=http_client or AsyncMock(spec=httpx.AsyncClient),
    )


async def test_production_never_delegates(monkeypatch):
    """Tower → should_delegate_to_remote always False."""
    identity = _make_identity("production", monkeypatch)
    coord = _make_coordinator(identity)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    assert await coord.should_delegate_to_remote(request) is False


async def test_development_delegates_when_nitro5_online(monkeypatch):
    """Nitro 5 + remote online → True."""
    identity = _make_identity("development", monkeypatch)
    presence = MagicMock(spec=PresenceTracker)
    presence.is_online.return_value = True
    coord = _make_coordinator(identity, presence=presence)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    assert await coord.should_delegate_to_remote(request) is True


async def test_development_no_delegate_when_offline(monkeypatch):
    """Nitro 5 + OFFLINE state → False."""
    identity = _make_identity("development", monkeypatch)
    presence = MagicMock(spec=PresenceTracker)
    presence.is_online.return_value = False
    coord = _make_coordinator(identity, presence=presence)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    assert await coord.should_delegate_to_remote(request) is False


async def test_scheduled_task_never_delegates(monkeypatch):
    """task_source=scheduled → False regardless."""
    identity = _make_identity("development", monkeypatch)
    presence = MagicMock(spec=PresenceTracker)
    presence.is_online.return_value = True
    coord = _make_coordinator(identity, presence=presence)
    request = TaskRequest(
        task_type=TaskType.GENERAL, prompt="test", task_source="scheduled"
    )
    assert await coord.should_delegate_to_remote(request) is False


async def test_adjusted_chain_deprioritizes_overloaded(monkeypatch):
    """85% Gemini usage → Gemini last."""
    identity = _make_identity("development", monkeypatch)
    state_reader = AsyncMock(spec=TwinStateReader)
    state_reader.get_usage = AsyncMock(return_value=UsageSummary(
        date="2026-06-15",
        providers={
            "gemini": ProviderUsageRecord(calls=1300),  # 1300/1500 = 86.7%
            "groq": ProviderUsageRecord(calls=100),
        },
    ))
    coord = _make_coordinator(identity, state_reader=state_reader)
    chain = await coord.get_adjusted_routing_chain(["gemini", "groq", "ollama"])
    assert chain[-1] == "gemini"
    assert chain[0] == "groq"


async def test_adjusted_chain_unchanged_when_state_none(monkeypatch):
    """state_reader returns None → default chain."""
    identity = _make_identity("development", monkeypatch)
    state_reader = AsyncMock(spec=TwinStateReader)
    state_reader.get_usage = AsyncMock(return_value=None)
    coord = _make_coordinator(identity, state_reader=state_reader)
    chain = await coord.get_adjusted_routing_chain(["gemini", "groq", "ollama"])
    assert chain == ["gemini", "groq", "ollama"]


async def test_adjusted_chain_unchanged_below_threshold(monkeypatch):
    """70% usage → chain unchanged."""
    identity = _make_identity("development", monkeypatch)
    state_reader = AsyncMock(spec=TwinStateReader)
    state_reader.get_usage = AsyncMock(return_value=UsageSummary(
        date="2026-06-15",
        providers={
            "gemini": ProviderUsageRecord(calls=1050),  # 1050/1500 = 70%
        },
    ))
    coord = _make_coordinator(identity, state_reader=state_reader)
    chain = await coord.get_adjusted_routing_chain(["gemini", "groq", "ollama"])
    assert chain == ["gemini", "groq", "ollama"]


async def test_delegate_to_remote_returns_response(monkeypatch):
    """successful delegation → DelegationResponse."""
    identity = _make_identity("development", monkeypatch)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "task_id": "abc-123",
        "accepted": True,
        "reason": "accepted",
        "provider": "gemini",
    }
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(return_value=mock_resp)
    coord = _make_coordinator(identity, http_client=client)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    result = await coord.delegate_to_remote(request, "100.106.80.49", 8001)
    assert isinstance(result, DelegationResponse)
    assert result.accepted is True


async def test_delegate_to_remote_returns_none_on_timeout(monkeypatch):
    """httpx timeout → None (no exception)."""
    identity = _make_identity("development", monkeypatch)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    coord = _make_coordinator(identity, http_client=client)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    result = await coord.delegate_to_remote(request, "100.106.80.49", 8001)
    assert result is None


async def test_delegate_to_remote_returns_none_on_connection_error(monkeypatch):
    """ConnectError → None."""
    identity = _make_identity("development", monkeypatch)
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    coord = _make_coordinator(identity, http_client=client)
    request = TaskRequest(task_type=TaskType.RESEARCH, prompt="test")
    result = await coord.delegate_to_remote(request, "100.106.80.49", 8001)
    assert result is None


async def test_accept_delegation_accepts_when_idle(monkeypatch):
    """Remote TOBOR idle → accepted=True."""
    identity = _make_identity("production", monkeypatch)
    coord = _make_coordinator(identity)
    delegation = DelegationRequest(
        task_id="abc-123",
        task_type=TaskType.RESEARCH,
        prompt="test",
        from_role=InstanceRole.DEVELOPMENT,
    )
    result = await coord.accept_delegation(delegation)
    assert result.accepted is True
    assert result.task_id == "abc-123"


async def test_delegation_timeout_from_env(monkeypatch):
    """DELEGATION_TIMEOUT_SECONDS=3 respected."""
    monkeypatch.setenv("DELEGATION_TIMEOUT_SECONDS", "3")
    identity = _make_identity("development", monkeypatch)
    coord = _make_coordinator(identity)
    assert coord._delegation_timeout == 3.0
