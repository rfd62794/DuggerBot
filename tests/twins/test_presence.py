"""Tests for duggerbot.twins.presence — Phase 3."""

from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from duggerbot.twins.models import (
    InstanceCapabilities,
    InstanceRole,
    Nitro5State,
    TwinHeartbeat,
    TwinRegistration,
    TwinStatus,
)
from duggerbot.twins.presence import (
    HEARTBEAT_INTERVAL_SECONDS,
    OFFLINE_THRESHOLD,
    STALE_THRESHOLD,
    PresenceTracker,
)


def _make_registration():
    caps = InstanceCapabilities(
        ollama_model="phi3.5:3.8b", mcp_port=8001, providers=["gemini"]
    )
    return TwinRegistration(
        role=InstanceRole.DEVELOPMENT,
        host="100.106.80.50",
        mcp_port=8001,
        capabilities=caps,
    )


def _make_heartbeat():
    return TwinHeartbeat(
        role=InstanceRole.DEVELOPMENT,
        host="100.106.80.50",
        version="0.1.0",
    )


def test_initial_state_unknown():
    """PresenceTracker starts in UNKNOWN."""
    tracker = PresenceTracker()
    status = tracker.get_status()
    assert status.state == Nitro5State.UNKNOWN


def test_register_sets_registered():
    """register() → state REGISTERED."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    status = tracker.get_status()
    assert status.state == Nitro5State.REGISTERED


def test_heartbeat_sets_online():
    """record_heartbeat() after register → ONLINE."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    tracker.record_heartbeat(_make_heartbeat())
    status = tracker.get_status()
    assert status.state == Nitro5State.ONLINE


def test_three_missed_heartbeats_stale():
    """90+ seconds no heartbeat → STALE."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    tracker.record_heartbeat(_make_heartbeat())
    # Simulate 100 seconds elapsed
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=100)
    tracker._last_heartbeat = stale_time
    status = tracker.get_status()
    assert status.state == Nitro5State.STALE


def test_five_missed_heartbeats_offline():
    """150+ seconds no heartbeat → OFFLINE."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    tracker.record_heartbeat(_make_heartbeat())
    # Simulate 160 seconds elapsed
    offline_time = datetime.now(timezone.utc) - timedelta(seconds=160)
    tracker._last_heartbeat = offline_time
    status = tracker.get_status()
    assert status.state == Nitro5State.OFFLINE


def test_heartbeat_resets_to_online_from_stale():
    """heartbeat after STALE → ONLINE."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    tracker.record_heartbeat(_make_heartbeat())
    # Force stale
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=100)
    tracker._last_heartbeat = stale_time
    tracker.get_status()  # compute stale
    assert tracker._state == Nitro5State.STALE
    # Send fresh heartbeat
    tracker.record_heartbeat(_make_heartbeat())
    status = tracker.get_status()
    assert status.state == Nitro5State.ONLINE


def test_get_status_returns_twin_status():
    """get_status() returns TwinStatus."""
    tracker = PresenceTracker()
    status = tracker.get_status()
    assert isinstance(status, TwinStatus)


def test_is_online_true_when_online():
    """is_online() True only when ONLINE."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    tracker.record_heartbeat(_make_heartbeat())
    assert tracker.is_online() is True


def test_is_online_false_when_stale():
    """is_online() False when STALE."""
    tracker = PresenceTracker()
    tracker.register(_make_registration())
    tracker.record_heartbeat(_make_heartbeat())
    stale_time = datetime.now(timezone.utc) - timedelta(seconds=100)
    tracker._last_heartbeat = stale_time
    assert tracker.is_online() is False


def test_is_online_false_when_unregistered():
    """is_online() False when UNKNOWN."""
    tracker = PresenceTracker()
    assert tracker.is_online() is False
