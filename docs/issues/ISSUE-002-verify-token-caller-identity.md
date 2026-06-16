**ISSUE-002: `verify_token()` must return `CallerIdentity`**

**Created by:** ADR-008
**Severity:** Medium
**Must close:** Before Phase 3 certifies
**Touches:** `duggerbot/mcp/auth.py`, `duggerbot/mcp/handlers.py`, `duggerbot/router/models.py`, `tests/mcp/test_auth.py` 

**Problem:**
`verify_token()` currently returns `None` on success or raises `HTTPException(401)` on failure. ADR-008 requires handlers to know the caller identity (CLAUDE vs DEVIN) to apply per-caller routing rules — Devin's production tool calls must route to cheapest provider only, never Claude API budget.

**Fix:**
1. Add `CallerIdentity(str, Enum)` to `router/models.py` with values `CLAUDE` and `DEVIN` 
2. Add `DEVIN_AUTH_TOKEN` to `.env.example` and `config/instance.yaml` 
3. Update `verify_token()` to return `CallerIdentity` — match against `MCP_AUTH_TOKEN` → `CLAUDE`, match against `DEVIN_AUTH_TOKEN` → `DEVIN`, no match → `401` 
4. Update `Depends(verify_token)` signatures in `handlers.py` to receive `CallerIdentity` 
5. Update `test_auth.py` — existing 8 tests need return value assertions, add 2 new tests: `test_claude_token_returns_claude_identity` and `test_devin_token_returns_devin_identity` 

**Routing restriction (handlers.py):**
When `caller == CallerIdentity.DEVIN` and tool is `research`, `fast_lookup`, or `local_inference` — override routing to exclude `claude` from the provider chain regardless of `routing.yaml`. Never touch Claude API budget on Devin's behalf.
