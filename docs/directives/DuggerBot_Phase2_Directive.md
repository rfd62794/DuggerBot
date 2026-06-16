# DuggerBot — Phase 2 Directive: MCP Server Layer

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run `uv run pytest` before touching any file.
> Must report **35 passed, 0 failed, 0 skipped** (Phase 1 certified floor).
> If count differs, stop and report — do not proceed.

---

## §0 Context

Phase 1 delivered the routing brain: ProviderRegistry, HealthChecker, UsageLedger,
ModelRouter — certified at 35/0/0, 97% coverage.

Phase 2 delivers the **MCP server layer** — the endpoint Claude uses to call DuggerBot's
tools directly. OQ-001 is resolved: **SSE transport, port 8001.** This matches the
existing Claude Desktop config and enables Tower ↔ Nitro 5 access over Tailscale.

**What Phase 2 produces:**
- FastAPI app with SSE transport serving five tools Claude can call
- Auth guard on every endpoint — ADR-007 enforced in code, not policy
- Tool schemas that define what Claude sees when listing DuggerBot's tools
- Handlers that delegate to ModelRouter and return MCP-typed responses
- 45 tests, 0 failures, 0 skipped
- 80%+ coverage per module, 80%+ overall

**What Phase 2 does NOT produce:**
- Real API calls to providers (Phase 1 router returns RouteResult only — execution comes later)
- Twin protocol logic (Phase 3)
- RALPH research loop (Phase 4)
- Telegram integration
- Any retry or backoff logic

**Reference before writing any MCP code:**
`C:\Github\PrivyBot` contains a working MCP server implementation with SSE transport.
Read it. DuggerBot's transport architecture must match the established pattern.
Do not invent a new MCP transport approach — use what already works on these machines.

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/mcp/server.py` | Stub → Implement | FastAPI app, SSE transport, lifespan, /health endpoint |
| `duggerbot/mcp/auth.py` | Stub → Implement | Bearer token validation — dependency injected on every endpoint |
| `duggerbot/mcp/tools.py` | Stub → Implement | Five MCP tool definitions as schema objects |
| `duggerbot/mcp/handlers.py` | Stub → Implement | Execute tool calls, delegate to router, return TextContent |
| `.env.example` | Modify | Add `DB_PATH` variable |
| `tests/mcp/test_server.py` | Stub → Implement | 12 tests |
| `tests/mcp/test_auth.py` | Stub → Implement | 8 tests |
| `tests/mcp/test_tools.py` | Stub → Implement | 8 tests |
| `tests/mcp/test_handlers.py` | Stub → Implement | 17 tests |
| `docs/state/current.md` | Modify | Update as final step only |

**Dependency to add before writing any code:**
```
uv add mcp
```
This modifies `pyproject.toml` and `uv.lock`. Both changes are expected and correct.
Commit both after adding.

**Read-only — do not touch under any circumstances:**
All `duggerbot/router/` files (Phase 1 complete, certified),
`duggerbot/twins/`, `duggerbot/ralph/`, `duggerbot/soul/`,
all `docs/adr/`, all soul documents, `.gitignore`

Report before fixing any bug found in a read-only file.

---

## §2 Implementation

Implement in this order. Run tests for each module before proceeding to the next.

---

### 2.1 Add `DB_PATH` to `.env.example`

Add before the MCP section:

```env
# Database
DB_PATH=                         # Path to SQLite usage ledger. Default: duggerbot.db in repo root
```

Also add to `config/instance.yaml` schema under the database section.

---

### 2.2 `duggerbot/mcp/auth.py`

Bearer token validation. Single responsibility: check the token, reject or pass through.
Implemented as a FastAPI dependency — injected into every endpoint that requires auth.

> ⚠️ **RULE:** auth.py uses `secrets.compare_digest` for token comparison — never `==`.
> Timing-safe comparison prevents timing attacks. This is not optional.

> ⚠️ **RULE:** auth.py reads `MCP_AUTH_TOKEN` from environment at call time, not at
> module import. If the env var is missing, raise `RuntimeError` with a clear message —
> do not silently allow unauthenticated access.

```python
import secrets
import os
from fastapi import HTTPException, Header
from typing import Annotated


async def verify_token(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """
    FastAPI dependency. Validates bearer token against MCP_AUTH_TOKEN env var.
    Raises HTTP 401 for any authentication failure.
    Never raises for internal errors — converts them to 401.
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
```

---

### 2.3 `duggerbot/mcp/tools.py`

Five MCP tool definitions. Single responsibility: describe what tools exist and what
their input schemas are. No execution logic here.

> ⚠️ **RULE:** tools.py contains zero business logic. It is a schema registry.
> If any tool definition requires importing from router/, that import is wrong.
> Tool definitions are pure data — names, descriptions, JSON schemas.

Define each tool using the MCP SDK's `Tool` type (reference PrivyBot for the exact
import path). The five tools:

| Tool name | Description | Required params | Optional params |
|---|---|---|---|
| `research` | Route a research query to the best available provider (Gemini primary) | `query: str` | `context_size: int = 0` |
| `fast_lookup` | Route a fast lookup to the speed tier (Groq primary) | `query: str` | — |
| `local_inference` | Run a prompt on the local model (Ollama). Private tasks only. | `prompt: str` | — |
| `get_provider_status` | Return health and quota state for all providers | — | — |
| `get_cost_today` | Return Claude API spend today vs the $0.25 daily cap | — | — |

Expose a single function `get_tool_list()` that returns all five as a list.
The `list_tools` handler in server.py calls this function.

---

### 2.4 `duggerbot/mcp/handlers.py`

Execute tool calls. Delegates to ModelRouter, HealthChecker, and UsageLedger.
Returns MCP `TextContent` lists. Single responsibility: map tool name → execution → response.

> ⚠️ **RULE:** handlers.py never accesses the database directly. It calls
> UsageLedger methods only. Direct SQLite in a handler is a bug.

> ⚠️ **RULE:** All provider errors (ProviderExhaustedError, BudgetExceededError)
> are caught here and returned as error TextContent — never as HTTP exceptions.
> The MCP protocol communicates errors through content, not HTTP status codes.

```python
from mcp.types import TextContent  # reference PrivyBot for exact import
from duggerbot.router.models import (
    TaskRequest, TaskType, ProviderExhaustedError, BudgetExceededError
)
from duggerbot.router.router import ModelRouter
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger
from duggerbot.router.registry import ProviderRegistry


async def handle_research(
    router: ModelRouter, arguments: dict
) -> list[TextContent]:
    """Route research query. Returns RouteResult as TextContent."""
    # Build TaskRequest with TaskType.RESEARCH
    # Call router.route()
    # Return TextContent with provider and model info
    # Catch ProviderExhaustedError → return error TextContent

async def handle_fast_lookup(
    router: ModelRouter, arguments: dict
) -> list[TextContent]:
    """Route fast lookup. Groq preferred per routing.yaml."""

async def handle_local_inference(
    router: ModelRouter, arguments: dict
) -> list[TextContent]:
    """Route to Ollama. require_local=True on TaskRequest."""

async def handle_get_provider_status(
    health: HealthChecker,
    registry: ProviderRegistry,
) -> list[TextContent]:
    """Check all providers. Return status dict as formatted TextContent."""

async def handle_get_cost_today(
    ledger: UsageLedger,
) -> list[TextContent]:
    """Return today's Claude API cost and remaining budget as TextContent."""


# Handler dispatch table — server.py uses this
TOOL_HANDLERS: dict[str, str] = {
    "research": "handle_research",
    "fast_lookup": "handle_fast_lookup",
    "local_inference": "handle_local_inference",
    "get_provider_status": "handle_get_provider_status",
    "get_cost_today": "handle_get_cost_today",
}
```

The `call_tool` handler in server.py receives the tool name, looks it up in this
dispatch table, and routes to the correct handler function. Unknown tool names raise
`ValueError("Unknown tool: {name}")`.

---

### 2.5 `duggerbot/mcp/server.py`

FastAPI app with MCP SSE transport. Single responsibility: run the server,
wire dependencies, expose endpoints. No business logic here.

> ⚠️ **RULE:** server.py does not contain routing decisions, tool schemas, or
> auth logic. Those live in router.py, tools.py, and auth.py respectively.
> server.py wires them together — nothing more.

> ⚠️ **RULE:** Reference `C:\Github\PrivyBot` for the exact SSE transport pattern.
> Do not invent a new approach. The lifespan pattern, SSE endpoint, and messages
> endpoint must match the architecture already working on Tower and Nitro 5.

**Server structure:**

```python
from contextlib import asynccontextmanager
from pathlib import Path
import os
import yaml
import httpx
from fastapi import FastAPI, Depends
from duggerbot.mcp.auth import verify_token
from duggerbot.mcp.tools import get_tool_list
from duggerbot.mcp.handlers import TOOL_HANDLERS, handle_research  # etc
from duggerbot.router.registry import ProviderRegistry
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger
from duggerbot.router.router import ModelRouter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all dependencies at startup. Clean up at shutdown."""
    # 1. Load ProviderRegistry from config/providers.yaml
    # 2. Initialize UsageLedger with DB_PATH from env (default: "duggerbot.db")
    # 3. Create httpx.AsyncClient for HealthChecker
    # 4. Load routing config from config/routing.yaml
    # 5. Create ModelRouter
    # Store all in app.state
    yield
    # Close httpx client on shutdown


# /health endpoint — no auth required
# Returns: {"status": "ok", "name": "TOBOR", "version": "0.1.0",
#           "instance": INSTANCE_ROLE, "providers": count_of_enabled_providers}

# SSE endpoint — auth required (Depends(verify_token))
# Uses MCP SSE transport from PrivyBot pattern

# Messages endpoint — auth required
# Uses MCP SSE transport from PrivyBot pattern
```

**Constants:**
```python
SERVER_NAME = "duggerbot"
SERVER_VERSION = "0.1.0"
TOBOR_IDENTITY = "TOBOR"
DEFAULT_DB_PATH = "duggerbot.db"
```

---

## §3 Test Anchors

All tests mock external dependencies. No real HTTP. No real SQLite on disk (`tmp_path`).
No real API keys. No actual MCP SSE connections in unit tests — test the FastAPI
layer with `httpx.AsyncClient` and `app` directly.

Target: **45 passing, 0 failed, 0 skipped**

---

### `tests/mcp/test_auth.py` — 8 tests

| Test | Behaviour |
|---|---|
| `test_valid_token_passes` | Correct token → no exception raised |
| `test_missing_header_401` | No Authorization header → HTTPException 401 |
| `test_non_bearer_scheme_401` | "Basic abc123" → HTTPException 401 |
| `test_invalid_token_value_401` | Wrong token string → HTTPException 401 |
| `test_empty_token_401` | "Bearer " with empty string → HTTPException 401 |
| `test_whitespace_stripped_still_invalid` | "Bearer   " (spaces) → HTTPException 401 |
| `test_timing_safe_comparison_used` | Verify `secrets.compare_digest` called, not `==` |
| `test_missing_env_var_raises_runtime_error` | MCP_AUTH_TOKEN unset → RuntimeError |

---

### `tests/mcp/test_tools.py` — 8 tests

| Test | Behaviour |
|---|---|
| `test_tool_list_has_five_tools` | `get_tool_list()` returns list of length 5 |
| `test_all_tools_have_name` | Every tool has a non-empty string name |
| `test_all_tools_have_description` | Every tool has a non-empty description |
| `test_research_requires_query` | research inputSchema has "query" in required |
| `test_fast_lookup_requires_query` | fast_lookup inputSchema has "query" in required |
| `test_local_inference_requires_prompt` | local_inference inputSchema has "prompt" in required |
| `test_get_provider_status_no_required_params` | get_provider_status required is empty or absent |
| `test_get_cost_today_no_required_params` | get_cost_today required is empty or absent |

---

### `tests/mcp/test_handlers.py` — 17 tests

Mock `ModelRouter`, `HealthChecker`, `UsageLedger`, and `ProviderRegistry`.
No real routing or DB access.

| Test | Behaviour |
|---|---|
| `test_research_builds_research_task_type` | handle_research creates TaskRequest with TaskType.RESEARCH |
| `test_research_returns_text_content_list` | Return value is list of TextContent |
| `test_research_includes_provider_in_response` | RouteResult.provider appears in response text |
| `test_research_context_size_passed_through` | context_size argument flows into TaskRequest |
| `test_fast_lookup_builds_fast_lookup_task_type` | handle_fast_lookup uses TaskType.FAST_LOOKUP |
| `test_local_inference_sets_require_local_true` | handle_local_inference sets require_local=True on TaskRequest |
| `test_local_inference_builds_local_inference_task_type` | Uses TaskType.LOCAL_INFERENCE |
| `test_provider_exhausted_returns_error_content` | ProviderExhaustedError → TextContent with error message, no exception raised |
| `test_budget_exceeded_returns_error_content` | BudgetExceededError → TextContent with error, no exception raised |
| `test_get_provider_status_calls_check_all` | handle_get_provider_status calls health.check_all() |
| `test_get_provider_status_returns_all_providers` | Response includes all 5 provider names |
| `test_get_cost_today_calls_get_daily_summary` | handle_get_cost_today calls ledger.get_daily_summary() |
| `test_get_cost_today_includes_cap` | Response includes the $0.25 cap value |
| `test_get_cost_today_includes_remaining` | Response includes remaining budget |
| `test_unknown_tool_raises_value_error` | Calling dispatch with unknown name → ValueError |
| `test_tool_handlers_map_has_five_entries` | TOOL_HANDLERS dict has exactly 5 keys |
| `test_tool_handler_keys_match_tool_names` | TOOL_HANDLERS keys match names from get_tool_list() |

---

### `tests/mcp/test_server.py` — 12 tests

Use `httpx.AsyncClient` with the FastAPI `app`. Mock the lifespan dependencies.
Do not test SSE streaming — test that endpoints exist and auth works.

| Test | Behaviour |
|---|---|
| `test_health_endpoint_returns_200` | GET /health → 200 |
| `test_health_response_includes_name` | Response JSON has "name": "TOBOR" |
| `test_health_response_includes_version` | Response JSON has "version" key |
| `test_health_response_includes_instance_role` | Response JSON has "instance" key |
| `test_health_response_includes_provider_count` | Response JSON has "providers" as integer |
| `test_health_requires_no_auth` | GET /health without token → 200 (not 401) |
| `test_sse_endpoint_exists` | GET /sse returns something other than 404 |
| `test_sse_requires_auth` | GET /sse without token → 401 |
| `test_messages_endpoint_exists` | POST /messages returns something other than 404 |
| `test_messages_requires_auth` | POST /messages without token → 401 |
| `test_server_name_constant` | SERVER_NAME == "duggerbot" |
| `test_tobor_identity_constant` | TOBOR_IDENTITY == "TOBOR" |

---

## §4 Completion Criteria

All items must be true before Phase 2 is complete. No exceptions.

- [ ] `uv run pytest tests/mcp/` reports **45 passed, 0 failed, 0 skipped**
- [ ] `uv run pytest --cov=duggerbot/mcp --cov-report=term-missing --cov-fail-under=80` passes
- [ ] Per-module coverage from `--cov-report=json` — paste results:
  - `mcp/server.py` ≥ 80%
  - `mcp/auth.py` ≥ 80%
  - `mcp/tools.py` ≥ 80%
  - `mcp/handlers.py` ≥ 80%
- [ ] Full suite `uv run pytest` reports **80+ passed, 0 failed, 0 skipped** (Phase 1 + Phase 2)
- [ ] `mcp` package added via `uv add mcp`, `uv.lock` updated and committed
- [ ] `DB_PATH` added to `.env.example` and `config/instance.yaml`
- [ ] `/health` endpoint returns 200 with TOBOR identity (manual verification)
- [ ] Auth guard rejects request without token (manual: `curl http://localhost:8001/sse` → 401)
- [ ] Auth guard accepts request with correct token (manual: `curl -H "Authorization: Bearer <token>" http://localhost:8001/sse`)
- [ ] All handler errors (ProviderExhaustedError, BudgetExceededError) return TextContent — never HTTP 500
- [ ] `TOOL_HANDLERS` keys exactly match tool names from `get_tool_list()`
- [ ] `docs/state/current.md` updated to reflect Phase 2 certified

**Proof required (paste into completion report):**
```
Full pytest output: exact line showing "X passed, 0 failed, 0 skipped"
Coverage output: per-module table from --cov-report=term-missing
curl /health output: raw JSON response
curl /sse (no auth): raw response showing 401
```

Agent summaries are not accepted. Raw terminal output only.

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 2 — MCP Server Layer |
| Pre-flight floor | 35/0/0 (Phase 1 certified) |
| Target floor | 45/0/0 (Phase 2 only) |
| Full suite target | 80+/0/0 (Phase 1 + Phase 2) |
| Coverage | 80%+ per module, 80%+ overall |
| Transport | SSE — reference PrivyBot for exact pattern |
| Port | 8001 (from MCP_PORT env var) |
| Auth | Bearer token — `secrets.compare_digest` — no unauthenticated endpoints except /health |
| Tools | research, fast_lookup, local_inference, get_provider_status, get_cost_today |
| Handler errors | Return TextContent, never HTTP 500 |
| Dependency to add | `uv add mcp` before any code |
| PrivyBot reference | `C:\Github\PrivyBot` — working MCP SSE pattern |
| DB_PATH default | `"duggerbot.db"` in repo root |
| OQ-001 | Resolved: SSE |
| Open | OQ-002 (Nitro 5 Ollama benchmark — non-blocking), OQ-003, OQ-004, OQ-005 |
| Issue to track | ISSUE-001 (router.py coverage debt — close before Phase 4) |
| Read-only | All `duggerbot/router/` files, twins/, ralph/, soul/, all ADRs, soul documents, .gitignore |
| Next phase | Phase 3 — Twin Protocol |
