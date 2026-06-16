# DuggerBot — Phase 3 Directive: Twin Protocol

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP — TWO-STAGE PRE-FLIGHT:**
>
> **Stage 1: Resolve ISSUE-002 first.**
> Before running any tests, implement the CallerIdentity change from ISSUE-002:
> - Add `CallerIdentity(str, Enum)` to `duggerbot/router/models.py`
> - Add `DEVIN_AUTH_TOKEN` to `.env.example` and `config/instance.yaml`
> - Update `verify_token()` in `duggerbot/mcp/auth.py` to return `CallerIdentity`
> - Update `tests/mcp/test_auth.py` — existing 8 tests need return value assertions,
>   add `test_claude_token_returns_claude_identity` and
>   `test_devin_token_returns_devin_identity`
> - Update handler signatures in `duggerbot/mcp/handlers.py` that use
>   `Depends(verify_token)` to receive `CallerIdentity`
> - Add routing restriction in handlers: when `caller == CallerIdentity.DEVIN`,
>   exclude `claude` from provider chain on research/fast_lookup/local_inference
>
> **Stage 2: Confirm test floor.**
> Run `uv run pytest` after ISSUE-002 resolution.
> Must report **≥92 passed, 0 failed, 0 skipped** before proceeding.
> (90 Phase 1+2 + 2 new CallerIdentity tests = 92 minimum.)
> If count differs, stop and report.

---

## §0 Context

Phase 2 delivered the MCP server layer — FastAPI app, auth guard, tool schemas,
handlers — certified at 90/0/0, 93% coverage.

Phase 3 delivers the **Twin Protocol** — the coordination layer that makes Tower
and Nitro 5 aware of each other, prevents API quota conflicts, and enforces the
five-level hierarchy from ADR-008.

**Architecture decision (scope simplification):**
Twin protocol endpoints mount as `/twin/*` routes on the **existing MCP server**
(port 8001) via FastAPI `APIRouter`. There is no separate presence server process.
This avoids a second NSSM service and reuses the existing auth infrastructure.
`/twin/heartbeat GET` is the only unauthenticated endpoint — it is an explicit,
documented exception to ADR-007 (liveness check only, no data exposed).

**What Phase 3 produces:**
- `twins/models.py` — Pydantic schemas for the twin protocol
- `twins/identity.py` — Instance role and capability profile
- `twins/presence.py` — Heartbeat tracking (Tower-side state machine)
- `twins/state.py` — REST client: reads Tower's usage and provider state
- `twins/router.py` — FastAPI APIRouter: all `/twin/*` endpoints
- `twins/coordinator.py` — Task authority, delegation handshake, routing adjustment
- `mcp/server.py` modified — mounts twin router
- 52 new tests, 0 failures, 0 skipped
- 80%+ coverage per module, 80%+ overall

**What Phase 3 does NOT produce:**
- RALPH research loop (Phase 4)
- Morning dispatch or data ponds (Phase 4)
- Actual API calls to AI providers through the twin protocol
- NSSM service changes — those happen at deployment, not in code

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/router/models.py` | Modify (ISSUE-002) | Add `CallerIdentity` enum |
| `duggerbot/mcp/auth.py` | Modify (ISSUE-002) | Return `CallerIdentity`, add DEVIN_AUTH_TOKEN support |
| `duggerbot/mcp/handlers.py` | Modify (ISSUE-002) | Receive `CallerIdentity`, restrict Devin routing |
| `duggerbot/twins/models.py` | New | Twin protocol Pydantic schemas |
| `duggerbot/twins/identity.py` | Stub → Implement | Instance role and capabilities |
| `duggerbot/twins/presence.py` | Stub → Implement | Tower heartbeat tracker and state machine |
| `duggerbot/twins/state.py` | Stub → Implement | REST client for Tower state endpoints |
| `duggerbot/twins/router.py` | New | FastAPI APIRouter — all `/twin/*` endpoints |
| `duggerbot/twins/coordinator.py` | Stub → Implement | Task authority and delegation |
| `duggerbot/mcp/server.py` | Modify | Mount twin router on existing app |
| `.env.example` | Modify | Add `DELEGATION_TIMEOUT_SECONDS`, `STATE_REQUEST_TIMEOUT_SECONDS`, `DEVIN_AUTH_TOKEN` |
| `config/instance.yaml` | Modify | Add timeout vars and DEVIN_AUTH_TOKEN schema |
| `tests/mcp/test_auth.py` | Modify (ISSUE-002) | Update 8 tests, add 2 new |
| `tests/twins/test_models.py` | Stub → Implement | 8 tests |
| `tests/twins/test_identity.py` | Stub → Implement | 7 tests |
| `tests/twins/test_presence.py` | Stub → Implement | 10 tests |
| `tests/twins/test_state.py` | Stub → Implement | 8 tests |
| `tests/twins/test_router.py` | New | 7 tests |
| `tests/twins/test_coordinator.py` | Stub → Implement | 12 tests |
| `docs/state/current.md` | Modify | Update as final step only |

**Read-only — do not touch:**
All `duggerbot/ralph/`, `duggerbot/soul/`, all `docs/adr/`,
soul documents, `.gitignore`, `config/providers.yaml`, `config/routing.yaml`

Report before fixing any bug found in a read-only file.

---

## §2 Implementation

Implement in this order. Run the relevant test file after each module.
Do not proceed past a failing test.

---

### 2.1 ISSUE-002 Resolution (router/models.py, mcp/auth.py, mcp/handlers.py)

**`duggerbot/router/models.py`** — add to existing file:

```python
class CallerIdentity(str, Enum):
    CLAUDE = "claude"
    DEVIN = "devin"
```

> ⚠️ **RULE:** CallerIdentity goes in router/models.py, not mcp/models.py.
> It is consumed by both the MCP layer and the twin coordinator. Keeping it
> in router/models.py avoids a circular import. Do not move it.

**`duggerbot/mcp/auth.py`** — update `verify_token()` signature and return:

```python
async def verify_token(
    authorization: Annotated[str | None, Header()] = None,
) -> CallerIdentity:
    """
    Returns CallerIdentity.CLAUDE if MCP_AUTH_TOKEN matches.
    Returns CallerIdentity.DEVIN if DEVIN_AUTH_TOKEN matches.
    Raises HTTP 401 for any other case.
    DEVIN_AUTH_TOKEN may be unset — if so, Devin access is disabled.
    """
```

**`duggerbot/mcp/handlers.py`** — update handler signatures and add routing guard:

```python
async def handle_research(
    router: ModelRouter,
    arguments: dict,
    caller: CallerIdentity = CallerIdentity.CLAUDE,
) -> list[TextContent]:
    """
    When caller is DEVIN: exclude 'claude' from provider chain.
    Build a modified TaskRequest or instruct the router to skip Claude API.
    Never consume Claude API budget on Devin's behalf.
    """
```

The Devin routing restriction applies to `handle_research`, `handle_fast_lookup`,
and `handle_local_inference`. `handle_get_provider_status` and
`handle_get_cost_today` are unrestricted — read-only, no budget impact.

---

### 2.2 `.env.example` additions

```env
# Agent authentication
DEVIN_AUTH_TOKEN=                # Auth token for Devin MCP access. Leave blank to disable.

# Twin protocol timeouts (configurable — no ADR needed to change)
DELEGATION_TIMEOUT_SECONDS=5     # Max wait for Remote TOBOR task delegation response
STATE_REQUEST_TIMEOUT_SECONDS=2  # Max wait for Tower usage state before routing blind
```

---

### 2.3 `duggerbot/twins/models.py` (NEW)

> ⚠️ **RULE:** twins/models.py imports nothing from duggerbot except
> `duggerbot.router.models.TaskType` and `CallerIdentity`. Zero other
> internal imports. It is a schema file.

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
from duggerbot.router.models import TaskType, CallerIdentity


class InstanceRole(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"


class Nitro5State(str, Enum):
    UNKNOWN = "unknown"
    REGISTERED = "registered"
    ONLINE = "online"
    STALE = "stale"       # 3 missed heartbeats (90s)
    OFFLINE = "offline"   # 5 missed heartbeats (150s)


class InstanceCapabilities(BaseModel):
    ollama_model: str
    mcp_port: int
    providers: list[str]


class TwinRegistration(BaseModel):
    role: InstanceRole
    host: str
    mcp_port: int
    capabilities: InstanceCapabilities
    registered_at: datetime = Field(default_factory=datetime.utcnow)


class TwinHeartbeat(BaseModel):
    role: InstanceRole
    host: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str


class TwinStatus(BaseModel):
    state: Nitro5State
    role: InstanceRole | None = None
    host: str | None = None
    last_seen: datetime | None = None
    latency_ms: float | None = None


class DelegationRequest(BaseModel):
    task_id: str
    task_type: TaskType
    prompt: str
    from_role: InstanceRole
    timeout_seconds: float = 5.0


class DelegationResponse(BaseModel):
    task_id: str
    accepted: bool
    reason: str | None = None
    provider: str | None = None   # Which provider handled it, if accepted


class ProviderUsageRecord(BaseModel):
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class UsageSummary(BaseModel):
    date: str                                      # YYYY-MM-DD
    providers: dict[str, ProviderUsageRecord]      # provider_name → usage
```

---

### 2.4 `duggerbot/twins/identity.py`

Single responsibility: know which instance this is and produce its profile.

> ⚠️ **RULE:** identity.py reads from environment at instantiation time.
> It never writes to environment. It never makes network calls.
> Pure config reading — nothing more.

```python
import os
from duggerbot.twins.models import InstanceRole, InstanceCapabilities, TwinHeartbeat
from duggerbot.router.models import TaskType


class TwinIdentity:
    def __init__(self) -> None:
        role_str = os.environ.get("INSTANCE_ROLE", "development")
        self._role = InstanceRole(role_str)
        self._ollama_model = os.environ.get("OLLAMA_MODEL", "phi3.5:3.8b")
        self._mcp_port = int(os.environ.get("MCP_PORT", "8001"))
        self._version = "0.1.0"

    def get_role(self) -> InstanceRole: ...
    def is_production(self) -> bool: ...
    def is_development(self) -> bool: ...

    def get_capabilities(self) -> InstanceCapabilities:
        """Return this instance's capability profile."""

    def get_heartbeat(self) -> TwinHeartbeat:
        """Return a heartbeat payload identifying this instance."""
```

---

### 2.5 `duggerbot/twins/presence.py`

Single responsibility: Tower-side state machine tracking Nitro 5's presence.

This module runs on Tower only. It is called by the twin router when
registration and heartbeat requests arrive. It maintains Nitro 5's state
in memory (not SQLite — presence state is ephemeral, not historical).

> ⚠️ **RULE:** presence.py never makes outbound network calls. It only
> receives and tracks. The network call to register WITH Tower lives in
> coordinator.py. Do not reverse this.

```python
from datetime import datetime, timedelta
from duggerbot.twins.models import (
    TwinRegistration, TwinHeartbeat, TwinStatus, Nitro5State, InstanceRole
)


HEARTBEAT_INTERVAL_SECONDS = 30
STALE_THRESHOLD = 3    # missed heartbeats → STALE
OFFLINE_THRESHOLD = 5  # missed heartbeats → OFFLINE


class PresenceTracker:
    """Tower-side tracker for Nitro 5 presence. In-memory only."""

    def __init__(self) -> None:
        self._registration: TwinRegistration | None = None
        self._last_heartbeat: datetime | None = None
        self._state: Nitro5State = Nitro5State.UNKNOWN

    def register(self, registration: TwinRegistration) -> None:
        """Accept Nitro 5 registration. Sets state to REGISTERED."""

    def record_heartbeat(self, heartbeat: TwinHeartbeat) -> None:
        """Update last_heartbeat timestamp. Sets state to ONLINE."""

    def get_status(self) -> TwinStatus:
        """Compute current state based on time since last heartbeat."""
        # Compute missed_beats = (now - last_heartbeat) / interval
        # ONLINE: missed_beats < STALE_THRESHOLD
        # STALE: STALE_THRESHOLD ≤ missed_beats < OFFLINE_THRESHOLD
        # OFFLINE: missed_beats ≥ OFFLINE_THRESHOLD
        # UNKNOWN: never registered

    def is_online(self) -> bool:
        """True only when state is ONLINE."""
```

---

### 2.6 `duggerbot/twins/state.py`

Single responsibility: HTTP client that reads Tower's state endpoints.
Used by Local TOBOR (Nitro 5) only. Tower does not call itself.

> ⚠️ **RULE:** state.py never raises on network failure. All methods return
> `None` on timeout, connection error, or 4xx/5xx response. Caller decides
> what to do with None. Coordination failure must never block routing.

> ⚠️ **RULE:** state.py takes an `httpx.AsyncClient` as a constructor
> parameter. Never create the client internally.

```python
import os
import httpx
from duggerbot.twins.models import UsageSummary


class TwinStateReader:
    def __init__(
        self,
        tower_host: str,
        mcp_port: int,
        auth_token: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._base_url = f"http://{tower_host}:{mcp_port}"
        self._auth_token = auth_token
        self._client = http_client
        self._timeout = float(os.environ.get("STATE_REQUEST_TIMEOUT_SECONDS", "2"))

    async def get_usage(self) -> UsageSummary | None:
        """GET /twin/state/usage. Returns None on any failure."""

    async def get_provider_statuses(self) -> dict | None:
        """GET /twin/state/providers. Returns None on any failure."""

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth_token}"}
```

---

### 2.7 `duggerbot/twins/router.py` (NEW)

FastAPI APIRouter exposing all `/twin/*` endpoints. Mounted on the existing
MCP server in `mcp/server.py`. Role-conditional endpoints: Tower-only
endpoints are registered but return 403 when called on a development instance.

> ⚠️ **RULE:** router.py contains zero business logic. It receives HTTP,
> calls the appropriate module (PresenceTracker, UsageLedger, TwinCoordinator),
> and returns a response. All logic lives in the modules it calls.

**Endpoints:**

| Method | Path | Auth | Instance | Description |
|---|---|---|---|---|
| GET | `/twin/heartbeat` | None | Both | Liveness check — returns this instance's heartbeat |
| POST | `/twin/register` | Required | Tower only | Nitro 5 registers its presence |
| POST | `/twin/heartbeat` | Required | Tower only | Nitro 5 sends heartbeat |
| GET | `/twin/nitro5/status` | Required | Tower only | Returns current Nitro 5 state |
| GET | `/twin/state/usage` | Required | Tower only | Returns today's usage from UsageLedger |
| GET | `/twin/state/providers` | Required | Tower only | Returns current provider health |
| POST | `/twin/delegate` | Required | Both | Accept or reject a delegation request |

**Tower-only enforcement:**
```python
async def _require_production(identity: TwinIdentity = Depends(get_identity)):
    if identity.is_development():
        raise HTTPException(status_code=403, detail="Tower only")
```

---

### 2.8 `duggerbot/twins/coordinator.py`

Single responsibility: task authority decisions and delegation handshake.

> ⚠️ **RULE:** coordinator.py never makes routing decisions about WHICH
> provider to use. That belongs to ModelRouter. Coordinator decides WHETHER
> to handle locally or delegate to the other twin.

> ⚠️ **RULE:** coordinator.py never raises on network failure when delegating.
> Delegation timeout → return None → caller handles locally. Always.

```python
import os
import asyncio
import httpx
from duggerbot.twins.models import (
    DelegationRequest, DelegationResponse, InstanceRole
)
from duggerbot.twins.identity import TwinIdentity
from duggerbot.twins.state import TwinStateReader
from duggerbot.twins.presence import PresenceTracker
from duggerbot.router.models import TaskRequest


SCHEDULED_TASK_TYPES = {"scheduled", "heartbeat", "morning_dispatch"}


class TwinCoordinator:
    def __init__(
        self,
        identity: TwinIdentity,
        state_reader: TwinStateReader | None,
        presence: PresenceTracker | None,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._identity = identity
        self._state_reader = state_reader
        self._presence = presence
        self._client = http_client
        self._delegation_timeout = float(
            os.environ.get("DELEGATION_TIMEOUT_SECONDS", "5")
        )

    async def should_delegate_to_remote(self, request: TaskRequest) -> bool:
        """
        Local TOBOR only. True if task should go to Remote TOBOR.
        Always False when:
        - This is Remote TOBOR (no further delegation)
        - Task is a scheduled type
        - Remote TOBOR is offline or unregistered
        """
        if self._identity.is_production():
            return False
        if getattr(request, "task_source", None) in SCHEDULED_TASK_TYPES:
            return False
        if self._presence is None:
            return False
        return self._presence.is_online()

    async def get_adjusted_routing_chain(
        self, default_chain: list[str]
    ) -> list[str]:
        """
        Check Tower's provider usage and deprioritize providers above 80%
        of their free tier daily limit. Returns modified chain.
        Returns default_chain unchanged if state unavailable.
        """
        if self._state_reader is None:
            return default_chain
        usage = await self._state_reader.get_usage()
        if usage is None:
            return default_chain
        # Move overloaded providers to end of chain
        # Threshold: 80% of free tier RPD limit (from providers.yaml)

    async def delegate_to_remote(
        self, request: TaskRequest, tower_host: str, mcp_port: int
    ) -> DelegationResponse | None:
        """
        POST /twin/delegate to Remote TOBOR.
        Returns None on timeout or connection failure.
        Respects DELEGATION_TIMEOUT_SECONDS.
        """

    async def accept_delegation(
        self, delegation: DelegationRequest
    ) -> DelegationResponse:
        """
        Remote TOBOR: evaluate and accept or reject an incoming delegation.
        Accept if not in a critical background cycle, reject otherwise.
        """
```

---

### 2.9 `duggerbot/mcp/server.py` modification

Add twin router mount. This is the only change to server.py in Phase 3.

```python
# Add to imports:
from duggerbot.twins.router import twin_router

# Add to app after existing route registrations:
app.include_router(twin_router, prefix="/twin")
```

> ⚠️ **RULE:** No other changes to mcp/server.py in this phase.
> The twin router mount is the only permitted modification.

---

## §3 Test Anchors

All tests mock external dependencies. No real HTTP. No real SQLite (`tmp_path`).
No real Tailscale. Presence state is in-memory — no persistence in tests.

Phase 3 target: **52 new tests**
Full suite target after Phase 3: **≥144 passed, 0 failed, 0 skipped**

---

### `tests/mcp/test_auth.py` — ISSUE-002 updates (existing file)

Update all 8 existing tests to assert return value is `CallerIdentity`.
Add 2 new tests:

| Test | Behaviour |
|---|---|
| `test_claude_token_returns_claude_identity` | MCP_AUTH_TOKEN match → returns `CallerIdentity.CLAUDE` |
| `test_devin_token_returns_devin_identity` | DEVIN_AUTH_TOKEN match → returns `CallerIdentity.DEVIN` |

---

### `tests/twins/test_models.py` — 8 tests

| Test | Behaviour |
|---|---|
| `test_instance_role_values` | PRODUCTION and DEVELOPMENT in InstanceRole |
| `test_nitro5_state_all_five_values` | UNKNOWN, REGISTERED, ONLINE, STALE, OFFLINE |
| `test_twin_heartbeat_timestamp_default` | timestamp auto-populated |
| `test_twin_registration_validates` | TwinRegistration accepts valid data |
| `test_delegation_request_validates` | DelegationRequest with TaskType |
| `test_delegation_response_rejected` | accepted=False with reason |
| `test_usage_summary_empty_providers` | providers dict can be empty |
| `test_provider_usage_record_defaults` | all fields default to 0 |

---

### `tests/twins/test_identity.py` — 7 tests

| Test | Behaviour |
|---|---|
| `test_production_role_from_env` | INSTANCE_ROLE=production → InstanceRole.PRODUCTION |
| `test_development_role_from_env` | INSTANCE_ROLE=development → InstanceRole.DEVELOPMENT |
| `test_invalid_role_raises` | INSTANCE_ROLE=invalid → ValueError |
| `test_is_production_true` | production instance → is_production() True |
| `test_is_development_true` | development instance → is_development() True |
| `test_get_heartbeat_includes_role` | heartbeat.role matches instance role |
| `test_get_capabilities_includes_ollama_model` | capabilities.ollama_model from env |

---

### `tests/twins/test_presence.py` — 10 tests

| Test | Behaviour |
|---|---|
| `test_initial_state_unknown` | PresenceTracker starts in UNKNOWN |
| `test_register_sets_registered` | register() → state REGISTERED |
| `test_heartbeat_sets_online` | record_heartbeat() after register → ONLINE |
| `test_three_missed_heartbeats_stale` | 90+ seconds no heartbeat → STALE |
| `test_five_missed_heartbeats_offline` | 150+ seconds no heartbeat → OFFLINE |
| `test_heartbeat_resets_to_online_from_stale` | heartbeat after STALE → ONLINE |
| `test_get_status_returns_twin_status` | get_status() returns TwinStatus |
| `test_is_online_true_when_online` | is_online() True only when ONLINE |
| `test_is_online_false_when_stale` | is_online() False when STALE |
| `test_is_online_false_when_unregistered` | is_online() False when UNKNOWN |

---

### `tests/twins/test_state.py` — 8 tests

| Test | Behaviour |
|---|---|
| `test_get_usage_returns_summary_on_200` | 200 response → UsageSummary |
| `test_get_usage_returns_none_on_timeout` | httpx timeout → None (no exception) |
| `test_get_usage_returns_none_on_connection_error` | ConnectError → None |
| `test_get_usage_returns_none_on_401` | 401 response → None |
| `test_get_provider_statuses_returns_dict_on_200` | 200 → dict |
| `test_get_provider_statuses_returns_none_on_timeout` | timeout → None |
| `test_timeout_respects_env_var` | STATE_REQUEST_TIMEOUT_SECONDS=1 used in client |
| `test_auth_header_sent` | Authorization: Bearer token in every request |

---

### `tests/twins/test_router.py` — 7 tests

| Test | Behaviour |
|---|---|
| `test_heartbeat_get_returns_200_no_auth` | GET /twin/heartbeat → 200 without token |
| `test_heartbeat_get_returns_role` | Response includes instance role |
| `test_register_requires_auth` | POST /twin/register without token → 401 |
| `test_state_usage_requires_auth` | GET /twin/state/usage without token → 401 |
| `test_tower_only_endpoint_on_dev_returns_403` | POST /twin/register on dev instance → 403 |
| `test_delegate_endpoint_accepts_post` | POST /twin/delegate → not 404 |
| `test_twin_router_mounted_on_mcp_app` | `/twin/heartbeat` route exists on main app |

---

### `tests/twins/test_coordinator.py` — 12 tests

| Test | Behaviour |
|---|---|
| `test_production_never_delegates` | Tower → should_delegate_to_remote always False |
| `test_development_delegates_when_nitro5_online` | Nitro 5 + Nitro 5 online → True |
| `test_development_no_delegate_when_offline` | Nitro 5 + OFFLINE state → False |
| `test_scheduled_task_never_delegates` | task_source=scheduled → False regardless |
| `test_adjusted_chain_deprioritizes_overloaded` | 85% Gemini usage → Gemini last |
| `test_adjusted_chain_unchanged_when_state_none` | state_reader returns None → default chain |
| `test_adjusted_chain_unchanged_below_threshold` | 70% usage → chain unchanged |
| `test_delegate_to_remote_returns_response` | successful delegation → DelegationResponse |
| `test_delegate_to_remote_returns_none_on_timeout` | httpx timeout → None (no exception) |
| `test_delegate_to_remote_returns_none_on_connection_error` | ConnectError → None |
| `test_accept_delegation_accepts_when_idle` | Remote TOBOR idle → accepted=True |
| `test_delegation_timeout_from_env` | DELEGATION_TIMEOUT_SECONDS=3 respected |

---

## §4 Completion Criteria

All items must be true before Phase 3 is complete. No exceptions.

- [ ] ISSUE-002 resolved: `CallerIdentity` in models.py, auth.py returns it, handlers restrict Devin routing
- [ ] `uv run pytest tests/mcp/test_auth.py` reports **10 passed, 0 failed, 0 skipped** (8 updated + 2 new)
- [ ] `uv run pytest tests/twins/` reports **52 passed, 0 failed, 0 skipped**
- [ ] Full suite: **≥144 passed, 0 failed, 0 skipped**
- [ ] Coverage: `--cov=duggerbot/twins --cov-fail-under=80` passes
- [ ] Per-module coverage (paste JSON report):
  - `twins/models.py` ≥ 80%
  - `twins/identity.py` ≥ 80%
  - `twins/presence.py` ≥ 80%
  - `twins/state.py` ≥ 80%
  - `twins/router.py` ≥ 80%
  - `twins/coordinator.py` ≥ 80%
- [ ] `DEVIN_AUTH_TOKEN`, `DELEGATION_TIMEOUT_SECONDS`, `STATE_REQUEST_TIMEOUT_SECONDS` in `.env.example`
- [ ] `/twin/heartbeat GET` returns 200 with no auth (manual: `curl localhost:8001/twin/heartbeat`)
- [ ] `/twin/register POST` returns 401 with no auth (manual: `curl -X POST localhost:8001/twin/register`)
- [ ] On a development instance, `/twin/register POST` with valid auth → 403 (Tower only)
- [ ] Devin routing restriction verified: research() with DEVIN token excludes `claude` from chain (test-enforced)
- [ ] ISSUE-001 (router.py coverage debt) — confirm still open, no regression
- [ ] `docs/state/current.md` updated to reflect Phase 3 certified

**Proof required (paste into completion report):**
```
Full pytest output: exact line showing "X passed, 0 failed, 0 skipped"
Coverage per-module table from --cov-report=term-missing
curl /twin/heartbeat: raw response
curl /twin/register (no auth): raw 401 response
```

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 3 — Twin Protocol |
| Pre-flight | Resolve ISSUE-002 first, then ≥92/0/0 |
| New test target | 52 tests |
| Full suite target | ≥144/0/0 |
| Coverage | 80%+ per module |
| Twin endpoints | Mounted at `/twin/*` on existing MCP server (port 8001) |
| Only unauthenticated endpoint | GET `/twin/heartbeat` — explicit ADR-007 exception |
| Tower-only endpoints | /register, /heartbeat POST, /nitro5/status, /state/*, (403 on dev) |
| Delegation timeout | `DELEGATION_TIMEOUT_SECONDS` env var, default 5 |
| State timeout | `STATE_REQUEST_TIMEOUT_SECONDS` env var, default 2 |
| Scheduled tasks | Never delegate — always Tower, always local |
| Devin routing | Excludes `claude` provider — never touches Claude API budget |
| Open issues | ISSUE-001 (router coverage, close before Phase 4), ISSUE-002 (resolve in pre-flight) |
| Deferred | TWIN_AUTH_TOKEN (future ADR), DUGGERWORKSHOP third twin |
| Read-only | ralph/, soul/, all ADRs, soul documents, .gitignore, providers.yaml, routing.yaml |
| Next phase | Phase 4 — RALPH Rebuilt |
