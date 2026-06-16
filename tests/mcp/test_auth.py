"""Tests for duggerbot.mcp.auth — Phase 2."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from duggerbot.mcp.auth import verify_token


TOKEN = "test-secret-token-abc123"


@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", TOKEN)


async def test_valid_token_passes():
    """Correct token → no exception raised."""
    await verify_token(authorization=f"Bearer {TOKEN}")


async def test_missing_header_401():
    """No Authorization header → HTTPException 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(authorization=None)
    assert exc_info.value.status_code == 401


async def test_non_bearer_scheme_401():
    """'Basic abc123' → HTTPException 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(authorization="Basic abc123")
    assert exc_info.value.status_code == 401


async def test_invalid_token_value_401():
    """Wrong token string → HTTPException 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(authorization="Bearer wrong-token")
    assert exc_info.value.status_code == 401


async def test_empty_token_401():
    """'Bearer ' with empty string → HTTPException 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(authorization="Bearer ")
    assert exc_info.value.status_code == 401


async def test_whitespace_stripped_still_invalid():
    """'Bearer   ' (spaces) → HTTPException 401."""
    with pytest.raises(HTTPException) as exc_info:
        await verify_token(authorization="Bearer   ")
    assert exc_info.value.status_code == 401


async def test_timing_safe_comparison_used():
    """Verify secrets.compare_digest called, not ==."""
    with patch("duggerbot.mcp.auth.secrets.compare_digest", return_value=True) as mock_cmp:
        await verify_token(authorization="Bearer some-token")
        mock_cmp.assert_called_once()


async def test_missing_env_var_raises_runtime_error(monkeypatch):
    """MCP_AUTH_TOKEN unset → RuntimeError."""
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN"):
        await verify_token(authorization="Bearer anything")
