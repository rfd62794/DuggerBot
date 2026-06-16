"""Tests for duggerbot.twins.models — Phase 3."""

from datetime import datetime

from duggerbot.twins.models import (
    DelegationRequest,
    DelegationResponse,
    InstanceCapabilities,
    InstanceRole,
    Nitro5State,
    ProviderUsageRecord,
    TwinHeartbeat,
    TwinRegistration,
    UsageSummary,
)
from duggerbot.router.models import TaskType


def test_instance_role_values():
    """PRODUCTION and DEVELOPMENT in InstanceRole."""
    assert InstanceRole.PRODUCTION == "production"
    assert InstanceRole.DEVELOPMENT == "development"


def test_nitro5_state_all_five_values():
    """UNKNOWN, REGISTERED, ONLINE, STALE, OFFLINE."""
    values = {s.value for s in Nitro5State}
    assert values == {"unknown", "registered", "online", "stale", "offline"}


def test_twin_heartbeat_timestamp_default():
    """timestamp auto-populated."""
    hb = TwinHeartbeat(
        role=InstanceRole.DEVELOPMENT,
        host="100.106.80.50",
        version="0.1.0",
    )
    assert isinstance(hb.timestamp, datetime)


def test_twin_registration_validates():
    """TwinRegistration accepts valid data."""
    caps = InstanceCapabilities(
        ollama_model="phi3.5:3.8b", mcp_port=8001, providers=["gemini", "groq"]
    )
    reg = TwinRegistration(
        role=InstanceRole.DEVELOPMENT,
        host="100.106.80.50",
        mcp_port=8001,
        capabilities=caps,
    )
    assert reg.role == InstanceRole.DEVELOPMENT
    assert reg.host == "100.106.80.50"


def test_delegation_request_validates():
    """DelegationRequest with TaskType."""
    req = DelegationRequest(
        task_id="abc-123",
        task_type=TaskType.RESEARCH,
        prompt="test query",
        from_role=InstanceRole.DEVELOPMENT,
    )
    assert req.task_type == TaskType.RESEARCH
    assert req.timeout_seconds == 5.0


def test_delegation_response_rejected():
    """accepted=False with reason."""
    resp = DelegationResponse(
        task_id="abc-123",
        accepted=False,
        reason="busy with scheduled task",
    )
    assert resp.accepted is False
    assert resp.reason == "busy with scheduled task"
    assert resp.provider is None


def test_usage_summary_empty_providers():
    """providers dict can be empty."""
    summary = UsageSummary(date="2026-06-15", providers={})
    assert summary.providers == {}


def test_provider_usage_record_defaults():
    """all fields default to 0."""
    record = ProviderUsageRecord()
    assert record.calls == 0
    assert record.tokens_in == 0
    assert record.tokens_out == 0
    assert record.cost_usd == 0.0
