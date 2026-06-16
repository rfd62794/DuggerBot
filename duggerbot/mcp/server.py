"""Start and run the FastAPI application that exposes MCP-compatible endpoints."""

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

from duggerbot.mcp.auth import verify_token
from duggerbot.mcp.handlers import (
    TOOL_HANDLERS,
    handle_fast_lookup,
    handle_get_cost_today,
    handle_get_provider_status,
    handle_local_inference,
    handle_research,
)
from duggerbot.mcp.tools import get_tool_list
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger
from duggerbot.router.registry import ProviderRegistry
from duggerbot.router.router import ModelRouter
from duggerbot.twins.router import twin_router

SERVER_NAME = "duggerbot"
SERVER_VERSION = "0.1.0"
TOBOR_IDENTITY = "TOBOR"
DEFAULT_DB_PATH = "duggerbot.db"


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
        return get_tool_list()

    @mcp_server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
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

    yield

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
        "version": SERVER_VERSION,
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
