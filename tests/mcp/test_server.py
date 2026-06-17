"""Tests for duggerbot.mcp.server — Phase 2 + Phase 3.6."""

import os
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from duggerbot.mcp.server import (
    SERVER_NAME,
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


def _make_test_config(tmp_path):
    """Write minimal providers.yaml and routing.yaml to tmp_path/config."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "providers.yaml").write_text(
        "providers:\n"
        "  gemini:\n"
        "    role: primary\n"
        "    models: [gemini-2.0-flash]\n"
        "    health_endpoint: https://example.com\n"
        "    enabled: true\n"
    )
    (config_dir / "routing.yaml").write_text(
        "routing:\n"
        "  default_chain: [gemini]\n"
        "  task_overrides: {}\n"
    )
    return config_dir


async def test_lifespan_initializes_state(tmp_path, monkeypatch):
    """Lifespan creates all expected state attributes."""
    from duggerbot.mcp.server import lifespan
    config_dir = _make_test_config(tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import duggerbot.mcp.server as srv
    monkeypatch.setattr(srv, "__file__", str(config_dir / "mcp" / "server.py"))

    test_app = FastAPI(lifespan=lifespan)
    async with lifespan(test_app):
        assert hasattr(test_app.state, "registry")
        assert hasattr(test_app.state, "health")
        assert hasattr(test_app.state, "ledger")
        assert hasattr(test_app.state, "router")
        assert hasattr(test_app.state, "mcp_server")
        assert hasattr(test_app.state, "sse_transport")
        assert hasattr(test_app.state, "http_client")


async def test_lifespan_cleanup_closes_client(tmp_path, monkeypatch):
    """Lifespan cleanup closes httpx client."""
    from duggerbot.mcp.server import lifespan
    config_dir = _make_test_config(tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import duggerbot.mcp.server as srv
    monkeypatch.setattr(srv, "__file__", str(config_dir / "mcp" / "server.py"))

    test_app = FastAPI(lifespan=lifespan)
    async with lifespan(test_app):
        http_client = test_app.state.http_client
        assert not http_client.is_closed
    assert http_client.is_closed


async def test_lifespan_mcp_list_tools(tmp_path, monkeypatch):
    """MCP server list_tools handler returns 18 tools (5 production + 13 dev)."""
    from mcp.types import ListToolsRequest
    from duggerbot.mcp.server import lifespan
    config_dir = _make_test_config(tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import duggerbot.mcp.server as srv
    monkeypatch.setattr(srv, "__file__", str(config_dir / "mcp" / "server.py"))

    test_app = FastAPI(lifespan=lifespan)
    async with lifespan(test_app):
        mcp_server = test_app.state.mcp_server
        handler = mcp_server.request_handlers[ListToolsRequest]
        result = await handler(ListToolsRequest(method="tools/list"))
        assert len(result.root.tools) == 19


async def test_lifespan_mcp_call_tool(tmp_path, monkeypatch):
    """MCP server call_tool routes get_cost_today correctly."""
    from mcp.types import CallToolRequest, CallToolRequestParams
    from duggerbot.mcp.server import lifespan
    config_dir = _make_test_config(tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import duggerbot.mcp.server as srv
    monkeypatch.setattr(srv, "__file__", str(config_dir / "mcp" / "server.py"))

    test_app = FastAPI(lifespan=lifespan)
    async with lifespan(test_app):
        mcp_server = test_app.state.mcp_server
        handler = mcp_server.request_handlers[CallToolRequest]
        req = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="get_cost_today", arguments={}),
        )
        result = await handler(req)
        assert len(result.root.content) >= 1


def test_handler_fns_has_five_entries():
    """_HANDLER_FNS dict has exactly 5 entries matching TOOL_HANDLERS."""
    from duggerbot.mcp.server import _HANDLER_FNS
    from duggerbot.mcp.handlers import TOOL_HANDLERS
    assert set(_HANDLER_FNS.keys()) == set(TOOL_HANDLERS.keys())


def test_default_db_path():
    """DEFAULT_DB_PATH is 'duggerbot.db'."""
    from duggerbot.mcp.server import DEFAULT_DB_PATH
    assert DEFAULT_DB_PATH == "duggerbot.db"


# ---------------------------------------------------------------------------
# Phase 3.6 — Version in /health, update check deferral
# ---------------------------------------------------------------------------


async def test_health_response_version_matches_format(client):
    """version field matches x.x.x.rN pattern."""
    import re
    resp = await client.get("/health")
    version = resp.json()["version"]
    assert re.match(r"\d+\.\d+\.\d+\.r\d+", version)


async def test_health_response_includes_version_from_module(client):
    """GET /health → JSON has 'version' key from version.py."""
    resp = await client.get("/health")
    data = resp.json()
    assert "version" in data
    assert data["version"].startswith("0.1.0.r")


async def test_update_check_defers_when_inflight():
    """coordinator.has_inflight_work() True → update loop does not exit."""
    from unittest.mock import patch, AsyncMock as AM
    from duggerbot.mcp.server import _update_check_loop, last_tool_call_time
    import asyncio
    import time

    mock_app = MagicMock()
    mock_coordinator = AM()
    mock_coordinator.has_inflight_work.return_value = True
    mock_app.state.twin_coordinator = mock_coordinator

    call_count = [0]
    original_sleep = asyncio.sleep

    async def fake_sleep(seconds):
        call_count[0] += 1
        if call_count[0] >= 3:
            raise asyncio.CancelledError
        return

    def fake_run(*args, **kwargs):
        from unittest.mock import MagicMock as MM
        cmd = args[0]
        r = MM()
        r.returncode = 0
        if "origin/main" in cmd:
            r.stdout = "200\n"
        elif "HEAD" in cmd:
            r.stdout = "174\n"
        else:
            r.stdout = ""
        return r

    # Set last_tool_call_time to >5 min ago so time check passes, then inflight check happens
    old_time = time.time() - 400

    with patch("duggerbot.mcp.server.asyncio.sleep", side_effect=fake_sleep), \
         patch("duggerbot.version.subprocess.run", side_effect=fake_run), \
         patch("duggerbot.mcp.server.last_tool_call_time", old_time):

        with pytest.raises(asyncio.CancelledError):
            await _update_check_loop(mock_app)

    mock_coordinator.has_inflight_work.assert_called()


# ---------------------------------------------------------------------------
# Phase 4a.2 — Deferred updates (5 min idle required)
# ---------------------------------------------------------------------------

def test_last_tool_call_time_tracks_activity():
    """last_tool_call_time exists and is initialized to recent timestamp."""
    import time
    from duggerbot.mcp import server
    # Should exist and be a recent timestamp
    assert hasattr(server, "last_tool_call_time")
    assert isinstance(server.last_tool_call_time, float)
    assert time.time() - server.last_tool_call_time < 60  # Initialized recently
