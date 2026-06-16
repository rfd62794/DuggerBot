"""Tests for duggerbot.twins.router — Phase 3."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from duggerbot.twins.router import twin_router
from duggerbot.twins.identity import TwinIdentity
from duggerbot.twins.models import InstanceRole
from duggerbot.twins.presence import PresenceTracker
from duggerbot.twins.coordinator import TwinCoordinator


TOKEN = "test-secret-token-abc123"


def _make_app(role: str):
    """Create a FastAPI app with twin_router mounted and mocked state."""
    app = FastAPI()
    app.include_router(twin_router, prefix="/twin")

    # Mock TwinIdentity
    identity = MagicMock(spec=TwinIdentity)
    identity.get_role.return_value = InstanceRole(role)
    identity.is_production.return_value = (role == "production")
    identity.is_development.return_value = (role == "development")
    app.state.twin_identity = identity

    # Mock PresenceTracker
    presence = MagicMock(spec=PresenceTracker)
    presence.get_status.return_value = MagicMock(
        model_dump=lambda: {"state": "unknown"}
    )
    app.state.presence_tracker = presence

    # Mock ledger
    ledger = AsyncMock()
    ledger.get_daily_summary = AsyncMock(return_value={})
    app.state.ledger = ledger

    # Mock health + registry
    health = AsyncMock()
    health.check_all = AsyncMock(return_value={})
    app.state.health = health

    registry = MagicMock()
    registry.list_enabled.return_value = []
    app.state.registry = registry

    # Mock coordinator
    from duggerbot.twins.models import DelegationResponse
    coordinator = AsyncMock(spec=TwinCoordinator)
    coordinator.accept_delegation = AsyncMock(return_value=DelegationResponse(
        task_id="mock", accepted=True, reason="mock",
    ))
    app.state.twin_coordinator = coordinator

    return app


@pytest.fixture
def production_app(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)
    return _make_app("production")


@pytest.fixture
def development_app(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)
    return _make_app("development")


async def test_heartbeat_get_returns_200_no_auth(production_app):
    """GET /twin/heartbeat → 200 without token."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.get("/twin/heartbeat")
        assert resp.status_code == 200


async def test_heartbeat_get_returns_role(production_app):
    """Response includes instance role."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.get("/twin/heartbeat")
        data = resp.json()
        assert data["role"] == "production"
        assert data["status"] == "ok"


async def test_register_requires_auth(production_app):
    """POST /twin/register without token → 401."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.post("/twin/register", json={})
        assert resp.status_code == 401


async def test_state_usage_requires_auth(production_app):
    """GET /twin/state/usage without token → 401."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.get("/twin/state/usage")
        assert resp.status_code == 401


async def test_tower_only_endpoint_on_dev_returns_403(development_app):
    """POST /twin/register on dev instance → 403 (not 404)."""
    async with AsyncClient(
        transport=ASGITransport(app=development_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/twin/register",
            json={},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 403


async def test_delegate_endpoint_accepts_post(production_app):
    """POST /twin/delegate → not 404."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/twin/delegate",
            json={
                "task_id": "abc-123",
                "task_type": "research",
                "prompt": "test",
                "from_role": "development",
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        # Should not be 404 — route exists
        assert resp.status_code != 404


async def test_register_post_accepted_on_production(production_app):
    """POST /twin/register on production with valid auth + valid body → 200."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/twin/register",
            json={
                "role": "development",
                "host": "100.106.80.50",
                "mcp_port": 8001,
                "capabilities": {
                    "ollama_model": "phi3.5:3.8b",
                    "mcp_port": 8001,
                    "providers": ["gemini"],
                },
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"


async def test_heartbeat_post_accepted_on_production(production_app):
    """POST /twin/heartbeat on production with valid auth → 200."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/twin/heartbeat",
            json={
                "role": "development",
                "host": "100.106.80.50",
                "version": "0.1.0",
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


async def test_nitro5_status_on_production(production_app):
    """GET /twin/nitro5/status on production → 200."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/twin/nitro5/status",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200


async def test_state_usage_on_production(production_app):
    """GET /twin/state/usage on production → 200."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/twin/state/usage",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "date" in data
        assert "providers" in data


async def test_state_providers_on_production(production_app):
    """GET /twin/state/providers on production → 200."""
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.get(
            "/twin/state/providers",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200


def test_twin_router_mounted_on_mcp_app():
    """Verify twin_router has /heartbeat route."""
    from duggerbot.twins.router import twin_router
    route_paths = [r.path for r in twin_router.routes]
    assert "/heartbeat" in route_paths


# ---------------------------------------------------------------------------
# Phase 3.6 — POST /twin/upgrade
# ---------------------------------------------------------------------------


async def test_upgrade_endpoint_defers_when_inflight(production_app):
    """has_inflight_work True → accepted False."""
    production_app.state.twin_coordinator.has_inflight_work = AsyncMock(return_value=True)
    async with AsyncClient(
        transport=ASGITransport(app=production_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/twin/upgrade",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False
        assert "in-flight" in data["reason"]


async def test_upgrade_endpoint_accepts_when_update_available(production_app, monkeypatch):
    """no inflight + update available → accepted True."""
    production_app.state.twin_coordinator.has_inflight_work = AsyncMock(return_value=False)

    def fake_run(*args, **kwargs):
        from unittest.mock import MagicMock as MM
        cmd = args[0]
        r = MM()
        if "origin/main" in cmd:
            r.returncode = 0
            r.stdout = "200\n"
        elif "HEAD" in cmd:
            r.returncode = 0
            r.stdout = "174\n"
        else:
            r.returncode = 0
            r.stdout = ""
        return r

    from unittest.mock import patch
    with patch("duggerbot.version.subprocess.run", side_effect=fake_run):
        async with AsyncClient(
            transport=ASGITransport(app=production_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/twin/upgrade",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["accepted"] is True
