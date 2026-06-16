# DuggerBot — Phase 1 Directive: Provider Router + Usage Ledger

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Phase 0 scaffold has no test floor — this is expected.
> Before touching any code file, run two checks in order:
>
> 1. `uv sync` — must exit 0. If it fails, stop and report.
> 2. `uv run pytest` — must report **0 errors** on collection. 0 passed is correct (no tests yet). Any collection error means the scaffold is broken — stop and report.
>
> Do not proceed until both checks pass clean.

---

## §0 Context

Phase 0 delivered the full repo scaffold: directory structure, ADRs, soul documents,
config stubs, pyproject.toml, and all test file stubs. No implementation exists yet.

Phase 1 delivers the **routing brain** — the layer that decides which provider handles
a given task. Phase 1 does NOT make actual API calls to providers. It routes, checks
health, tracks costs, and enforces budget. Execution against real provider APIs begins
in Phase 2 (MCP handlers) and Phase 4 (RALPH).

**What Phase 1 produces:**
- Five modules implementing the router layer with SRP
- `providers.yaml` and `routing.yaml` populated with real config
- 32 tests, 0 failures, 0 skipped
- 80%+ coverage per module, 80%+ overall

**What Phase 1 does NOT produce:**
- Real API calls to Gemini, Groq, OpenRouter, Ollama, or Claude
- MCP server endpoints
- Twin protocol logic
- RALPH research loop
- Ollama warm-up request (Phase 4)

**Deferred — do not add:**
- Retry logic with backoff (Phase 2)
- Rate limit tracking against provider quotas (Phase 2)
- Telegram notifications (Phase 4)
- Any feature not listed in §1

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/router/models.py` | Stub → Implement | Pydantic schemas — all five models |
| `duggerbot/router/registry.py` | Stub → Implement | Load providers.yaml, expose provider list |
| `duggerbot/router/health.py` | Stub → Implement | Poll provider health endpoints |
| `duggerbot/router/ledger.py` | Stub → Implement | SQLite usage tracking, cap enforcement |
| `duggerbot/router/router.py` | Stub → Implement | Route TaskRequest to RouteResult |
| `config/providers.yaml` | Stub → Populate | Real provider config per §2 |
| `config/routing.yaml` | Stub → Populate | Routing chain per §2 |
| `tests/router/test_models.py` | Stub → Implement | 7 tests |
| `tests/router/test_registry.py` | Stub → Implement | 6 tests |
| `tests/router/test_health.py` | Stub → Implement | 6 tests |
| `tests/router/test_ledger.py` | Stub → Implement | 7 tests |
| `tests/router/test_router.py` | Stub → Implement | 6 tests |
| `tests/conftest.py` | Stub → Implement | Shared fixtures for all router tests |
| `duggerbot/router/__init__.py` | Exists | Do not touch |
| `docs/state/current.md` | Exists | Update as final step only |

**Read-only — do not touch under any circumstances:**
`duggerbot/mcp/`, `duggerbot/twins/`, `duggerbot/ralph/`, `duggerbot/soul/`,
all `docs/adr/`, `SOUL.md`, `MEMORY.md`, `AGENTS.md`, `HEARTBEAT.md`,
`pyproject.toml`, `.env.example`, `.gitignore`

Report before fixing any bug found in a read-only file. Do not silently modify
out-of-scope files.

---

## §2 Implementation

Implement in this exact order. Run `uv run pytest tests/router/test_models.py` after
models.py. Run `uv run pytest tests/router/` after each subsequent file. Never move
to the next file with a failing test in the current one.

---

### 2.1 `config/providers.yaml`

Populate this file before writing any Python. The registry reads from it; tests
mock it. The schema drives everything in this phase.

```yaml
providers:
  gemini:
    role: primary
    models:
      - gemini-2.0-flash
      - gemini-1.5-flash
    free_tier:
      rpd: 1500
      rpm: 15
      tpm: 1000000
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "https://generativelanguage.googleapis.com/v1beta/models"

  groq:
    role: speed
    models:
      - llama-3.1-70b-versatile
      - mixtral-8x7b-32768
    free_tier:
      rpd: 6000
      rpm: 30
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "https://api.groq.com/openai/v1/models"

  openrouter:
    role: access
    models:
      - meta-llama/llama-3.1-70b-instruct
    cost_per_1k_tokens: 0.001
    enabled: true
    health_endpoint: "https://openrouter.ai/api/v1/models"

  ollama:
    role: local
    models:
      - phi3.5:3.8b
    cost_per_1k_tokens: 0.0
    enabled: true
    health_endpoint: "http://localhost:11434/api/tags"
    keep_alive: -1

  claude:
    role: reserved
    models:
      - claude-sonnet-4-6
    daily_cap_usd: 0.25
    cost_per_1k_input_tokens: 0.003
    cost_per_1k_output_tokens: 0.015
    enabled: true
    health_endpoint: "https://api.anthropic.com/v1/models"
```

---

### 2.2 `config/routing.yaml`

```yaml
routing:
  default_chain:
    - gemini
    - groq
    - ollama
    - openrouter
    - claude

  task_overrides:
    research:
      - gemini
      - openrouter
      - claude
    fast_lookup:
      - groq
      - gemini
      - openrouter
    local_inference:
      - ollama
      - groq
```

---

### 2.3 `duggerbot/router/models.py`

Define all Pydantic v2 schemas. No imports beyond `pydantic`, `enum`, `datetime`.
No network imports. No file I/O.

> ⚠️ **RULE:** models.py must import nothing from duggerbot. Zero internal imports.
> It is the base layer. Everything else imports from it. Never reverse this.

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    RESEARCH = "research"
    FAST_LOOKUP = "fast_lookup"
    LOCAL_INFERENCE = "local_inference"
    GENERAL = "general"


class FreeTier(BaseModel):
    rpd: int | None = None   # requests per day
    rpm: int | None = None   # requests per minute
    tpm: int | None = None   # tokens per minute


class Provider(BaseModel):
    name: str
    role: str                              # primary | speed | access | local | reserved
    models: list[str]
    free_tier: FreeTier | None = None
    cost_per_1k_tokens: float = 0.0
    cost_per_1k_input_tokens: float | None = None
    cost_per_1k_output_tokens: float | None = None
    daily_cap_usd: float | None = None    # Claude only
    enabled: bool = True
    health_endpoint: str
    keep_alive: int | None = None         # Ollama only


class ProviderStatus(BaseModel):
    name: str
    available: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime = Field(default_factory=datetime.utcnow)


class TaskRequest(BaseModel):
    task_type: TaskType
    prompt: str
    context_size: int = 0
    require_local: bool = False           # Force Ollama — private tasks only


class RouteResult(BaseModel):
    provider: str
    model: str
    task_type: TaskType
    fallback_chain: list[str] = Field(default_factory=list)
    budget_remaining_usd: float = 0.0


class ProviderExhaustedError(Exception):
    """All providers in the routing chain are unavailable."""


class BudgetExceededError(Exception):
    """Claude API daily cap would be exceeded."""


class ProviderUnavailableError(Exception):
    """A specific provider is unavailable."""
```

---

### 2.4 `duggerbot/router/registry.py`

Loads `providers.yaml` and exposes the provider list. Single responsibility:
config loading and provider lookup. No health checks. No routing decisions.

> ⚠️ **RULE:** registry.py reads config only. It never checks provider health
> and never makes routing decisions. Any logic beyond loading and exposing
> provider data belongs in a different file.

```python
from pathlib import Path
import yaml
from duggerbot.router.models import Provider


class ProviderRegistry:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._providers: dict[str, Provider] = {}
        self._routing_order: list[str] = []

    def load(self) -> None:
        """Load providers.yaml. Raises FileNotFoundError if missing."""
        # Parse YAML, build Provider objects, set _routing_order to
        # the order providers appear in the file.

    def get(self, name: str) -> Provider | None:
        """Return Provider for name, or None if unknown."""

    def list_enabled(self) -> list[Provider]:
        """Return all enabled providers in file order."""

    def get_routing_order(self) -> list[str]:
        """Return ordered provider names as they appear in config."""
```

---

### 2.5 `duggerbot/router/health.py`

Polls provider health endpoints. Returns `ProviderStatus`. Never raises on
provider failure — unavailability is expected, especially for Ollama.

> ⚠️ **RULE:** health.py never raises an exception for a provider being down.
> A failed poll returns `ProviderStatus(available=False, error=str(e))`.
> Exceptions from httpx (timeout, connection refused) are caught and converted.
> Ollama returning unhealthy is the expected case — 3% historical success rate.

> ⚠️ **RULE:** health.py takes an `httpx.AsyncClient` as a constructor parameter.
> Never create the client internally. This is what makes it testable.

```python
import httpx
from duggerbot.router.models import Provider, ProviderStatus


class HealthChecker:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def check(self, provider: Provider) -> ProviderStatus:
        """Poll provider health endpoint. Never raises — returns status."""
        # GET provider.health_endpoint with 5s timeout
        # 2xx → available=True
        # Non-2xx or exception → available=False, error=str

    async def check_all(self, providers: list[Provider]) -> dict[str, ProviderStatus]:
        """Check all providers. Returns dict[provider_name → ProviderStatus]."""
```

---

### 2.6 `duggerbot/router/ledger.py`

Tracks API usage in SQLite. Enforces Claude's $0.25/day cap. Single
responsibility: usage recording and budget enforcement. No routing logic.

> ⚠️ **RULE:** ledger.py enforces budget only for providers with `daily_cap_usd`
> set (currently only Claude). Other providers are tracked but never capped.
> The cap is read from the `Provider` object, not hardcoded.

> ⚠️ **RULE:** Daily rollover is date-based. "Today" means the current local date
> as a `YYYY-MM-DD` string. Yesterday's records must never count toward today's cap.

```python
import aiosqlite
from pathlib import Path
from datetime import date
from duggerbot.router.models import BudgetExceededError


SCHEMA = """
CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0.0,
    called_at TEXT NOT NULL,
    date TEXT NOT NULL
);
"""


class UsageLedger:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def initialize(self) -> None:
        """Create tables if not exist. Call once at startup."""

    async def record_call(
        self,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        """Write one usage record. date field is today's date."""

    async def get_today_cost(self, provider: str) -> float:
        """Return sum of cost_usd for provider on today's date."""

    async def check_budget(self, provider: str, daily_cap_usd: float,
                           estimated_cost: float) -> None:
        """Raise BudgetExceededError if today_cost + estimated_cost > cap."""

    async def get_daily_summary(self) -> dict[str, dict]:
        """Return {provider: {calls, tokens_in, tokens_out, cost_usd}} for today."""
```

---

### 2.7 `duggerbot/router/router.py`

Accepts a `TaskRequest`, applies routing chain, returns a `RouteResult`.
Consumes `ProviderRegistry`, `HealthChecker`, and `UsageLedger`.
Single responsibility: routing decisions only. No API calls. No config loading.

> ⚠️ **RULE:** router.py never calls any external API. It calls health.py to
> check availability and ledger.py to check budget. The actual provider API
> call happens in a later phase. Router's job ends at RouteResult.

> ⚠️ **RULE:** The routing chain for a given TaskRequest comes from routing.yaml
> via `routing_config` (injected as a dict). Never hardcode provider order here.

```python
import yaml
from pathlib import Path
from duggerbot.router.models import (
    TaskRequest, RouteResult, ProviderExhaustedError
)
from duggerbot.router.registry import ProviderRegistry
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger


class ModelRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        health: HealthChecker,
        ledger: UsageLedger,
        routing_config: dict,
    ) -> None:
        self._registry = registry
        self._health = health
        self._ledger = ledger
        self._routing_config = routing_config

    async def route(self, request: TaskRequest) -> RouteResult:
        """
        Route a TaskRequest to the best available provider.

        Chain resolution:
        1. If require_local=True → use local_inference chain from routing.yaml
        2. Look up task_overrides for request.task_type
        3. Fall back to default_chain if no override
        4. Walk chain: check health, check budget (Claude only), return first viable
        5. If all exhausted → raise ProviderExhaustedError
        """

    def _get_chain(self, request: TaskRequest) -> list[str]:
        """Return ordered provider names for this request."""

    @classmethod
    def from_config(
        cls,
        providers_path: Path,
        routing_path: Path,
        health: HealthChecker,
        ledger: UsageLedger,
    ) -> "ModelRouter":
        """Convenience constructor — loads both config files."""
```

---

## §3 Test Anchors

All tests mock external calls. No real HTTP. No real SQLite file on disk
(use `tmp_path` pytest fixture). No real API keys. Every provider call
is a `pytest-mock` patch or an `httpx.MockTransport`.

Target: **32 passing, 0 failed, 0 skipped**

---

### `tests/conftest.py`

```python
# Shared fixtures for all router tests

@pytest.fixture
def providers_yaml(tmp_path) -> Path:
    """Write a minimal providers.yaml to tmp_path and return the path."""

@pytest.fixture
def routing_yaml(tmp_path) -> Path:
    """Write a minimal routing.yaml to tmp_path and return the path."""

@pytest.fixture
def mock_http_client():
    """Return an httpx.AsyncClient backed by httpx.MockTransport."""

@pytest.fixture
async def ledger(tmp_path) -> UsageLedger:
    """Initialized UsageLedger backed by a tmp SQLite file."""
```

---

### `tests/router/test_models.py` — 7 tests

| Test | Behaviour |
|---|---|
| `test_task_type_values` | TaskType enum has RESEARCH, FAST_LOOKUP, LOCAL_INFERENCE, GENERAL |
| `test_provider_valid` | Provider validates with required fields |
| `test_provider_defaults` | enabled=True, cost=0.0, daily_cap_usd=None by default |
| `test_provider_status_defaults` | ProviderStatus.checked_at auto-populated |
| `test_task_request_require_local_default` | require_local defaults to False |
| `test_route_result_fallback_chain_default` | fallback_chain defaults to empty list |
| `test_invalid_task_type` | ValidationError raised for unknown task_type string |

---

### `tests/router/test_registry.py` — 6 tests

| Test | Behaviour |
|---|---|
| `test_load_valid_yaml` | Registry loads providers_yaml fixture without error |
| `test_missing_file_raises` | FileNotFoundError when config path does not exist |
| `test_get_known_provider` | get("gemini") returns Provider with correct role |
| `test_get_unknown_provider` | get("unknown") returns None |
| `test_list_enabled_excludes_disabled` | Provider with enabled=false excluded from list |
| `test_routing_order_matches_file` | get_routing_order() returns names in YAML order |

---

### `tests/router/test_health.py` — 6 tests

| Test | Behaviour |
|---|---|
| `test_healthy_provider_returns_available` | 200 response → ProviderStatus(available=True) |
| `test_unhealthy_provider_returns_unavailable` | 503 response → ProviderStatus(available=False) |
| `test_timeout_returns_unavailable` | httpx.TimeoutException → ProviderStatus(available=False) |
| `test_connection_error_returns_unavailable` | httpx.ConnectError → ProviderStatus(available=False) |
| `test_check_all_returns_all_providers` | check_all with 3 providers returns dict with 3 keys |
| `test_ollama_failure_does_not_raise` | Ollama connection refused → status not exception |

---

### `tests/router/test_ledger.py` — 7 tests

| Test | Behaviour |
|---|---|
| `test_initialize_creates_table` | initialize() runs without error, table exists |
| `test_get_today_cost_empty` | Returns 0.0 for provider with no records today |
| `test_record_and_retrieve_cost` | record_call() then get_today_cost() returns correct sum |
| `test_multiple_providers_tracked_independently` | Claude cost does not affect Gemini cost |
| `test_check_budget_within_cap` | No exception when today_cost + estimated < cap |
| `test_check_budget_exceeds_cap` | BudgetExceededError when today_cost + estimated > cap |
| `test_daily_rollover` | Record with yesterday's date does not count toward today's cap |

---

### `tests/router/test_router.py` — 6 tests

| Test | Behaviour |
|---|---|
| `test_routes_to_primary_when_healthy` | Gemini healthy → RouteResult.provider == "gemini" |
| `test_skips_unhealthy_falls_back` | Gemini unhealthy, Groq healthy → routes to Groq |
| `test_require_local_routes_to_ollama` | require_local=True → attempts Ollama first |
| `test_provider_exhausted_raises` | All providers unhealthy → ProviderExhaustedError |
| `test_claude_budget_exceeded_skipped` | Claude over cap → skipped in chain, exhausted if last |
| `test_fallback_chain_recorded` | RouteResult.fallback_chain includes all tried providers |

---

## §4 Completion Criteria

All items must be true before Phase 1 is complete. No exceptions.

- [ ] `uv run pytest tests/router/` reports **32 passed, 0 failed, 0 skipped**
- [ ] `uv run pytest --cov=duggerbot/router --cov-report=term-missing --cov-fail-under=80` passes
- [ ] `uv run pytest --cov=duggerbot/router --cov-report=json` produced — paste the per-module table:
  - `router/models.py` ≥ 80%
  - `router/registry.py` ≥ 80%
  - `router/health.py` ≥ 80%
  - `router/ledger.py` ≥ 80%
  - `router/router.py` ≥ 80%
- [ ] `config/providers.yaml` populated with all 5 providers per §2.1
- [ ] `config/routing.yaml` populated with default chain and task overrides per §2.2
- [ ] No hardcoded provider names, URLs, or costs in any `.py` file — all driven by config
- [ ] No real HTTP calls in any test — all mocked
- [ ] No real SQLite file path in any test — all use `tmp_path`
- [ ] `ProviderExhaustedError`, `BudgetExceededError`, `ProviderUnavailableError` defined in models.py
- [ ] Ollama failure path tested and confirmed non-raising (test_ollama_failure_does_not_raise)
- [ ] `docs/state/current.md` updated to reflect Phase 1 certified

**Proof required (paste into completion report):**

```
pytest output: exact line showing "32 passed, 0 failed, 0 skipped"
coverage output: per-module percentages from --cov-report=term-missing
```

Agent summaries are not accepted as proof. Raw terminal output only.

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 1 — Provider Router + Usage Ledger |
| Pre-flight floor | 0 tests (Phase 0 scaffold) |
| Target floor | 32/0/0 |
| Coverage requirement | 80%+ overall AND per-module |
| Providers | gemini, groq, openrouter, ollama, claude |
| Routing chain | gemini → groq → ollama → openrouter → claude |
| Claude cap | $0.25/day — enforced by UsageLedger.check_budget() |
| Ollama baseline | 3% success rate (PrivyBot evidence) — failure is expected |
| Config files | config/providers.yaml, config/routing.yaml |
| DB fixture | tmp_path — never a real file path in tests |
| OQ-002 status | Benchmark Nitro 5 Ollama model during this phase — phi3.5 vs qwen2.5:3b |
| Next phase | Phase 2 — MCP Server Layer |
| Read-only | mcp/, twins/, ralph/, soul/, all ADRs, soul documents, pyproject.toml |
