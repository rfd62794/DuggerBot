"""Start and run the FastAPI application that exposes MCP-compatible endpoints."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import yaml
from fastapi import Depends, FastAPI, Request, Response
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent

from duggerbot.heartbeat import heartbeat_loop
from duggerbot.mcp.auth import verify_token
from duggerbot.mcp.handlers import (
    DEV_TOOL_HANDLERS,
    TOOL_HANDLERS,
    handle_fast_lookup,
    handle_get_cost_today,
    handle_get_provider_status,
    handle_local_inference,
    handle_research,
)
from duggerbot.mcp.tools import get_dev_tool_list, get_tool_list
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger
from duggerbot.router.registry import ProviderRegistry
from duggerbot.router.router import ModelRouter
from duggerbot.twins.router import twin_router
from duggerbot.version import get_version_string

SERVER_NAME = "duggerbot"
TOBOR_IDENTITY = "TOBOR"
DEFAULT_DB_PATH = "duggerbot.db"


async def _update_check_loop(app: FastAPI) -> None:
    """Background task: periodically check for updates. Defers if in-flight work."""
    from duggerbot.version import is_update_available, apply_update_and_exit
    interval = int(os.environ.get("UPDATE_CHECK_INTERVAL_MINUTES", "60")) * 60
    retry = int(os.environ.get("UPDATE_CHECK_RETRY_MINUTES", "5")) * 60

    while True:
        await asyncio.sleep(interval)
        try:
            if not is_update_available():
                continue
            coordinator = getattr(app.state, "twin_coordinator", None)
            if coordinator and await coordinator.has_inflight_work():
                await asyncio.sleep(retry)
                continue
            apply_update_and_exit()
        except Exception:
            pass


_HANDLER_FNS = {
    "research": handle_research,
    "fast_lookup": handle_fast_lookup,
    "local_inference": handle_local_inference,
    "get_provider_status": handle_get_provider_status,
    "get_cost_today": handle_get_cost_today,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all dependencies at startup. Clean up at shutdown."""
    config_dir = Path(__file__).parent.parent.parent / "config"

    registry = ProviderRegistry(config_dir / "providers.yaml")
    registry.load()

    db_path = Path(os.environ.get("DB_PATH", DEFAULT_DB_PATH))
    ledger = UsageLedger(db_path)
    await ledger.initialize()

    http_client = httpx.AsyncClient()
    health = HealthChecker(http_client)

    routing_path = config_dir / "routing.yaml"
    with open(routing_path) as f:
        routing_config = yaml.safe_load(f)

    router = ModelRouter(registry, health, ledger, routing_config)

    app.state.registry = registry
    app.state.health = health
    app.state.ledger = ledger
    app.state.router = router
    app.state.http_client = http_client

    mcp_server = Server(SERVER_NAME)

    @mcp_server.list_tools()
    async def list_tools():
        return get_tool_list() + get_dev_tool_list()

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name in DEV_TOOL_HANDLERS:
            return await DEV_TOOL_HANDLERS[name](arguments)
        if name not in TOOL_HANDLERS:
            raise ValueError(f"Unknown tool: {name}")
        handler_name = TOOL_HANDLERS[name]
        handler_fn = _HANDLER_FNS[name]
        if name in ("get_provider_status",):
            return await handler_fn(health, registry)
        elif name in ("get_cost_today",):
            return await handler_fn(ledger)
        else:
            return await handler_fn(router, arguments)

    app.state.mcp_server = mcp_server
    app.state.sse_transport = SseServerTransport("/messages/")

    update_task = asyncio.create_task(_update_check_loop(app))
    heartbeat_task = asyncio.create_task(heartbeat_loop())

    yield

    heartbeat_task.cancel()
    update_task.cancel()
    await http_client.aclose()


app = FastAPI(lifespan=lifespan)
app.include_router(twin_router, prefix="/twin")


@app.get("/health")
async def health_endpoint(request: Request):
    """Health check — no auth required."""
    provider_count = len(request.app.state.registry.list_enabled()) if hasattr(request.app.state, "registry") else 0
    return {
        "status": "ok",
        "name": TOBOR_IDENTITY,
        "version": get_version_string(),
        "instance": os.environ.get("INSTANCE_ROLE", "unknown"),
        "providers": provider_count,
    }


@app.get("/sse", dependencies=[Depends(verify_token)])
async def sse_endpoint(request: Request):
    """SSE endpoint — auth required. Establishes MCP SSE connection."""
    sse_transport = request.app.state.sse_transport
    mcp_server = request.app.state.mcp_server
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )
    return Response()


@app.post("/messages/", dependencies=[Depends(verify_token)])
async def messages_endpoint(request: Request):
    """Messages endpoint — auth required. Handles MCP message posting."""
    sse_transport = request.app.state.sse_transport
    return await sse_transport.handle_post_message(request.scope, request.receive, request._send)
