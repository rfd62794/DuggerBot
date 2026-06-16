"""Tests for duggerbot.mcp.server — Phase 2."""

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from duggerbot.mcp.server import (
    SERVER_NAME,
    SERVER_VERSION,
    TOBOR_IDENTITY,
    app,
)
from duggerbot.router.models import Provider


@pytest.fixture
async def client(monkeypatch):
    """httpx.AsyncClient wired to the test app with mocked state."""
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("INSTANCE_ROLE", "development")

    registry = MagicMock()
    gemini = Provider(
        name="gemini", role="primary", models=["gemini-2.0-flash"],
        health_endpoint="https://example.com",
    )
    registry.list_enabled.return_value = [gemini]

    sse_transport = MagicMock()
    sse_transport.connect_sse = AsyncMock()
    sse_transport.handle_post_message = AsyncMock(return_value=httpx.Response(200))

    @asynccontextmanager
    async def _noop_lifespan(a: FastAPI):
        yield

    app.router.lifespan_context = _noop_lifespan

    app.state.registry = registry
    app.state.health = AsyncMock()
    app.state.ledger = AsyncMock()
    app.state.router = AsyncMock()
    app.state.http_client = AsyncMock()
    app.state.mcp_server = MagicMock()
    app.state.sse_transport = sse_transport

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_health_endpoint_returns_200(client):
    """GET /health → 200."""
    resp = await client.get("/health")
    assert resp.status_code == 200


async def test_health_response_includes_name(client):
    """Response JSON has 'name': 'TOBOR'."""
    resp = await client.get("/health")
    assert resp.json()["name"] == "TOBOR"


async def test_health_response_includes_version(client):
    """Response JSON has 'version' key."""
    resp = await client.get("/health")
    assert "version" in resp.json()


async def test_health_response_includes_instance_role(client):
    """Response JSON has 'instance' key."""
    resp = await client.get("/health")
    assert resp.json()["instance"] == "development"


async def test_health_response_includes_provider_count(client):
    """Response JSON has 'providers' as integer."""
    resp = await client.get("/health")
    data = resp.json()
    assert isinstance(data["providers"], int)
    assert data["providers"] == 1


async def test_health_requires_no_auth(client):
    """GET /health without token → 200 (not 401)."""
    resp = await client.get("/health")
    assert resp.status_code == 200


def test_sse_endpoint_exists():
    """GET /sse route is registered (not 404)."""
    routes = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/sse" in routes


async def test_sse_requires_auth(client):
    """GET /sse without token → 401."""
    resp = await client.get("/sse")
    assert resp.status_code == 401


async def test_messages_endpoint_exists(client):
    """POST /messages/ returns something other than 404."""
    resp = await client.post(
        "/messages/", headers={"Authorization": "Bearer test-token"}, content=b""
    )
    assert resp.status_code != 404


async def test_messages_requires_auth(client):
    """POST /messages/ without token → 401."""
    resp = await client.post("/messages/", content=b"")
    assert resp.status_code == 401


def test_server_name_constant():
    """SERVER_NAME == 'duggerbot'."""
    assert SERVER_NAME == "duggerbot"


def test_tobor_identity_constant():
    """TOBOR_IDENTITY == 'TOBOR'."""
    assert TOBOR_IDENTITY == "TOBOR"
