"""Validate bearer tokens on every incoming MCP request. Reject unauthenticated calls."""

import os
import secrets
from typing import Annotated

from fastapi import HTTPException, Header

from duggerbot.router.models import CallerIdentity


async def verify_token(
    authorization: Annotated[str | None, Header()] = None,
) -> CallerIdentity:
    """
    FastAPI dependency. Validates bearer token against MCP_AUTH_TOKEN and
    DEVIN_AUTH_TOKEN env vars.

    Returns CallerIdentity.CLAUDE if MCP_AUTH_TOKEN matches.
    Returns CallerIdentity.DEVIN if DEVIN_AUTH_TOKEN matches.
    Raises HTTP 401 for any other case.
    DEVIN_AUTH_TOKEN may be unset — if so, Devin access is disabled.
    """
    mcp_token = os.environ.get("MCP_AUTH_TOKEN")
    if not mcp_token:
        raise RuntimeError("MCP_AUTH_TOKEN environment variable not set")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token is empty")
    if secrets.compare_digest(token.encode(), mcp_token.encode()):
        return CallerIdentity.CLAUDE
    devin_token = os.environ.get("DEVIN_AUTH_TOKEN")
    if devin_token and secrets.compare_digest(token.encode(), devin_token.encode()):
        return CallerIdentity.DEVIN
    raise HTTPException(status_code=401, detail="Invalid token")
