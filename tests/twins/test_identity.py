"""Tests for duggerbot.twins.identity — Phase 3."""

import pytest

from duggerbot.twins.identity import TwinIdentity
from duggerbot.twins.models import InstanceRole


def test_production_role_from_env(monkeypatch):
    """INSTANCE_ROLE=production → InstanceRole.PRODUCTION."""
    monkeypatch.setenv("INSTANCE_ROLE", "production")
    identity = TwinIdentity()
    assert identity.get_role() == InstanceRole.PRODUCTION


def test_development_role_from_env(monkeypatch):
    """INSTANCE_ROLE=development → InstanceRole.DEVELOPMENT."""
    monkeypatch.setenv("INSTANCE_ROLE", "development")
    identity = TwinIdentity()
    assert identity.get_role() == InstanceRole.DEVELOPMENT


def test_invalid_role_raises(monkeypatch):
    """INSTANCE_ROLE=invalid → ValueError."""
    monkeypatch.setenv("INSTANCE_ROLE", "invalid")
    with pytest.raises(ValueError):
        TwinIdentity()


def test_is_production_true(monkeypatch):
    """production instance → is_production() True."""
    monkeypatch.setenv("INSTANCE_ROLE", "production")
    identity = TwinIdentity()
    assert identity.is_production() is True
    assert identity.is_development() is False


def test_is_development_true(monkeypatch):
    """development instance → is_development() True."""
    monkeypatch.setenv("INSTANCE_ROLE", "development")
    identity = TwinIdentity()
    assert identity.is_development() is True
    assert identity.is_production() is False


def test_get_heartbeat_includes_role(monkeypatch):
    """heartbeat.role matches instance role."""
    monkeypatch.setenv("INSTANCE_ROLE", "production")
    identity = TwinIdentity()
    hb = identity.get_heartbeat()
    assert hb.role == InstanceRole.PRODUCTION
    assert hb.version == "0.1.0"


def test_get_capabilities_includes_ollama_model(monkeypatch):
    """capabilities.ollama_model from env."""
    monkeypatch.setenv("INSTANCE_ROLE", "development")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:3b")
    identity = TwinIdentity()
    caps = identity.get_capabilities()
    assert caps.ollama_model == "qwen2.5:3b"
