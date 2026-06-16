"""Validate bearer tokens on every incoming MCP request. Reject unauthenticated calls."""

import os
import secrets
from typing import Annotated

from fastapi import HTTPException, Header


async def verify_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """
    FastAPI dependency. Validates bearer token against MCP_AUTH_TOKEN env var.
    Raises HTTP 401 for any authentication failure.
    """
    expected = os.environ.get("MCP_AUTH_TOKEN")
    if not expected:
        raise RuntimeError("MCP_AUTH_TOKEN environment variable not set")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token is empty")
    if not secrets.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid token")
