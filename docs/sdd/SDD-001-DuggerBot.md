# DuggerBot — System Design Document v0.1

*RFD IT Services Ltd. | June 2026 | Living Document*
*Spec-Driven | Test-Driven | Architect-in-the-Loop*

---

## §0 Identity

| Field | Value |
|---|---|
| Repo / shell name | DuggerBot |
| Agent soul name | TOBOR |
| Successor to | PrivyBot (retired, 604/0/0 certified floor, 33 phases) |
| Author | Robert Floyd Dugger |
| Brand | RFD IT Services Ltd. |
| License | Private |

**DuggerBot is the casing. TOBOR is what is alive inside it.**

TOBOR runs simultaneously on Tower (production) and Nitro 5 (development). Both instances
share one soul across two shells. They are twins, not copies. The soul document persists
across deployments. The codebase is rebuilt. The identity is not.

Reference: *Chappie* (soul transferred between shells). *Johnny 5* (aliveness, not hardware).

---

## §1 Purpose and Problem Statement

PrivyBot accumulated 33 phases, 131 MCP tools, and 604 tests before its fundamental
architecture became a liability. RALPH (the autonomous research agent) was catatonic more
often than functional — not because the concept failed, but because the infrastructure
beneath it was unreliable. Ollama keep_alive failures, tool bloat with unknown utilization,
no visibility into provider costs, and no coordination between Tower and Nitro 5.

DuggerBot solves four specific problems in order:

| Problem | Solution |
|---|---|
| Blind provider routing with unknown costs | Provider Router + Usage Ledger (Phase 1) |
| Claude cannot call Robert's local infrastructure | MCP Server Layer (Phase 2) |
| Tower and Nitro 5 have no awareness of each other | Twin Protocol (Phase 3) |
| RALPH is unreliable on Ollama | RALPH rebuilt on Gemini Flash (Phase 4) |

Each phase is independently deployable and certified before the next begins.

---

## §2 Mandatory Stack

These are non-negotiable. No alternatives. No exceptions without a superseding ADR.

| Requirement | Specification |
|---|---|
| Language | Python 3.12 minimum |
| Package manager | uv — never pip directly |
| Test framework | pytest |
| Coverage tool | pytest-cov |
| Coverage floor | 80% minimum — overall AND per-module |
| Providers | OpenRouter, Groq, Gemini, Claude API, Ollama |
| Validation | Pydantic v2 |
| HTTP client | httpx (async) |
| MCP server | FastAPI + uvicorn |
| Database | SQLite via aiosqlite |
| Config | YAML (providers, routing) + .env.local (per-instance) |
| Service management | NSSM (Tower only) |
| Network | Tailscale |

### Coverage Enforcement

Coverage is not a suggestion. It is a completion criterion for every phase.

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "--cov=duggerbot --cov-report=term-missing --cov-fail-under=80"
testpaths = ["tests"]

[tool.coverage.run]
source = ["duggerbot"]
branch = true

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "def __repr__",
]
```

Per-module enforcement: every phase directive must include a per-module coverage table
in its completion criteria. Any module below 80% is a failing phase regardless of
overall coverage. The agent must provide `--cov-report=json` output for per-module
verification.

---

## §3 Design Principles

### Single Responsibility (SRP) — Primary Principle

Every module, class, and function does exactly one thing. The name of every file
describes its single responsibility. If a file's name requires "and," it needs to
be split.

Correct: `health.py` checks provider health.
Incorrect: `health_and_routing.py`

SRP is enforced at code review and directive scope. The agent may not add responsibilities
to an existing file without an explicit directive instruction.

### What SOLID means here

SRP is mandatory. The other four principles (Open/Closed, Liskov, Interface Segregation,
Dependency Inversion) are not formal requirements. Good SRP naturally produces much of
their benefit. Do not add abstraction layers to satisfy SOLID checklist items — add them
when a real problem requires them.

### No Premature Abstraction

Build what the phase requires. Do not build "for flexibility." If a pattern repeats
three times in production, extract it. Not before.

### Test-First Discipline

Tests are written before implementation is accepted. Coverage is not an afterthought.
If the phase directive does not have test anchors for a component, the component
is not in scope.

---

## §4 Provider Stack

| Provider | Role | Tier | Free Tier Limits | Notes |
|---|---|---|---|---|
| Gemini Flash | Primary inference | Free first | 1500 RPD, 1M TPM, 15 RPM | RALPH's primary engine. Long context. Research synthesis. |
| Groq | Speed tier | Free | 6000 RPD, 30 RPM (model-dependent) | Fast structured outputs. Tool calls where latency matters. |
| OpenRouter | Access tier | Pay-as-you-go | Varies by model | Overflow. Specific models not available elsewhere. |
| Ollama | Local / private | Free (local) | Hardware-limited | Fallback only. Private tasks. Never primary. |
| Claude API | Reserved | Paid | $0.25/day hard cap | Used last. Tracked. Cap enforced by UsageLedger. |

### Provider Priority Chain

```
Task arrives → Check Gemini quota → Route to Gemini (if available)
            → Gemini at limit → Route to Groq
            → Groq at limit → Check Ollama health → Route to Ollama (if healthy)
            → Ollama unhealthy → Route to OpenRouter
            → Check Claude API budget → Route to Claude (if cap not exceeded)
            → All exhausted → Return ProviderExhaustedError
```

### Ollama Constraints

Ollama is demoted to fallback tier. It is never the primary or default route.
Model selection per instance:

- Tower: `phi3.5:3.8b` (fast load, reliable on i5-7500 + 32GB)
- Nitro 5: `qwen2.5:3b` or `phi3.5:3.8b` (benchmarked during Phase 1)

All Ollama API calls must include `"keep_alive": -1` in the request body.
A warm-up request must fire on service start before RALPH begins polling.
This is the lesson from PrivyBot. It is not optional.

### OpenRouter Usage Pattern

OpenRouter uses an OpenAI-compatible API. Use the `openai` package with:

```python
base_url = "https://openrouter.ai/api/v1"
api_key = OPENROUTER_API_KEY
```

No separate OpenRouter SDK. The `openai` package is the client.

---

## §5 Architecture Overview

DuggerBot has four layers. Each layer is built in a separate phase.
Each layer depends on the one below it. No layer is merged with another.

```
┌─────────────────────────────────────────────────┐
│  Phase 4: RALPH                                 │
│  Async research loop | 5 ponds | morning        │
│  dispatch | Gemini Flash primary                │
├─────────────────────────────────────────────────┤
│  Phase 3: Twin Protocol                         │
│  Presence | shared state | role authority       │
│  Tower ↔ Nitro 5 coordination                  │
├─────────────────────────────────────────────────┤
│  Phase 2: MCP Server Layer                      │
│  Claude-callable tools | FastAPI | auth         │
│  research() fast_lookup() get_status()          │
├─────────────────────────────────────────────────┤
│  Phase 1: Provider Router + Usage Ledger        │
│  Registry | health | routing | cost tracking    │
│  $0.25/day cap enforcement                      │
└─────────────────────────────────────────────────┘
```

---

## §6 Repo Structure

```
DuggerBot/
│
├── SOUL.md                      # TOBOR's identity document (see §8)
├── MEMORY.md                    # Long-term curated memory (seeded from PrivyBot)
├── AGENTS.md                    # Operational playbook for the agent
├── HEARTBEAT.md                 # Pending tasks queue for RALPH
├── AGENT_CONTRACT.md            # DuggerBot's own architectural contract
├── README.md
├── pyproject.toml
├── .env.example                 # Schema only — never commit real values
├── .env.local                   # Per-instance config — gitignored
├── .gitignore
├── .coveragerc                  # Coverage config (mirrors pyproject.toml)
│
├── memory/                      # Daily memory logs
│   └── YYYY-MM-DD.md            # Raw daily log — one file per day
│
├── config/
│   ├── providers.yaml           # Provider registry — models, limits, costs
│   ├── routing.yaml             # Task-type → provider mapping rules
│   └── instance.yaml            # Schema for per-instance .env.local values
│
├── duggerbot/
│   ├── __init__.py
│   │
│   ├── router/                  # Phase 1 — Provider Router
│   │   ├── __init__.py
│   │   ├── registry.py          # Load providers.yaml, expose provider list
│   │   ├── health.py            # Poll each provider, return availability
│   │   ├── ledger.py            # SQLite-backed usage tracker, cap enforcement
│   │   ├── router.py            # Route task to provider, enforce fallback chain
│   │   └── models.py            # Pydantic models: Provider, TaskRequest, RouteResult
│   │
│   ├── mcp/                     # Phase 2 — MCP Server
│   │   ├── __init__.py
│   │   ├── server.py            # FastAPI app, MCP protocol, startup/shutdown
│   │   ├── auth.py              # Token validation — no unauthenticated endpoints
│   │   ├── tools.py             # Tool schemas: research, fast_lookup, etc.
│   │   └── handlers.py          # Tool call execution — delegates to router
│   │
│   ├── twins/                   # Phase 3 — Twin Protocol
│   │   ├── __init__.py
│   │   ├── identity.py          # INSTANCE_ROLE, capabilities, instance profile
│   │   ├── presence.py          # Heartbeat endpoint, poll other instance
│   │   ├── state.py             # Read Tower SQLite from Nitro 5 via Tailscale
│   │   └── coordinator.py       # Task authority model, delegation handshake
│   │
│   ├── ralph/                   # Phase 4 — RALPH Research Agent
│   │   ├── __init__.py
│   │   ├── loop.py              # Async research loop, Gemini primary
│   │   ├── heartbeat.py         # Poll HEARTBEAT.md, batch pending tasks
│   │   ├── dispatch.py          # Morning briefing from pond data
│   │   └── ponds/               # Data pond schemas (one file = one source)
│   │       ├── __init__.py
│   │       ├── base.py          # BasePond abstract — shared refresh interface
│   │       ├── youtube_analytics.py
│   │       ├── youtube_calendar.py
│   │       ├── blog_calendar.py
│   │       ├── itch_analytics.py
│   │       └── ga4.py
│   │
│   └── soul/                    # Soul document interface
│       ├── __init__.py
│       ├── soul.py              # Load and expose SOUL.md content
│       └── memory.py            # Read/write MEMORY.md and daily logs
│
├── scripts/
│   ├── migrate_privybot.py      # Phase 0: PrivyBot DB audit + migration
│   ├── nssm_deploy.ps1          # Tower NSSM service deployment
│   ├── dev_start.sh             # Nitro 5 development start script
│   └── decommission_privybot.ps1 # PrivyBot succession ritual (run once)
│
├── docs/
│   ├── adr/
│   │   ├── ADR-001.md           # Gemini Flash is RALPH's primary engine
│   │   ├── ADR-002.md           # Ollama demoted to fallback
│   │   ├── ADR-003.md           # Tower is authoritative twin
│   │   ├── ADR-004.md           # n8n permanently tombstoned
│   │   ├── ADR-005.md           # Claude API $0.25/day hard cap
│   │   ├── ADR-006.md           # DuggerBot is personal infrastructure, not a platform
│   │   └── ADR-007.md           # Auth tokens required on MCP server from day one
│   ├── sdd/
│   │   └── SDD-001-DuggerBot.md # This document
│   └── state/
│       └── current.md           # Phase state file — updated on every phase completion
│
└── tests/
    ├── conftest.py              # Shared fixtures, mock providers, test config
    ├── router/
    │   ├── test_registry.py
    │   ├── test_health.py
    │   ├── test_ledger.py
    │   ├── test_router.py
    │   └── test_models.py
    ├── mcp/
    │   ├── test_server.py
    │   ├── test_auth.py
    │   ├── test_tools.py
    │   └── test_handlers.py
    ├── twins/
    │   ├── test_identity.py
    │   ├── test_presence.py
    │   ├── test_state.py
    │   └── test_coordinator.py
    ├── ralph/
    │   ├── test_loop.py
    │   ├── test_heartbeat.py
    │   ├── test_dispatch.py
    │   └── ponds/
    │       ├── test_base.py
    │       ├── test_youtube_analytics.py
    │       ├── test_youtube_calendar.py
    │       ├── test_blog_calendar.py
    │       ├── test_itch_analytics.py
    │       └── test_ga4.py
    └── soul/
        ├── test_soul.py
        └── test_memory.py
```

---

## §7 Component Map (SRP)

Every component has exactly one job. The job is stated in one sentence.

### Phase 1 — Router

| Component | File | Single Responsibility |
|---|---|---|
| ProviderRegistry | `router/registry.py` | Load `providers.yaml` and expose the provider list with their models and limits. |
| HealthChecker | `router/health.py` | Poll each provider's health endpoint and return current availability status. |
| UsageLedger | `router/ledger.py` | Track usage per provider per day in SQLite and enforce the Claude API $0.25/day cap. |
| ModelRouter | `router/router.py` | Accept a TaskRequest, apply routing rules, check health and budget, return a RouteResult. |
| RouterModels | `router/models.py` | Define Pydantic schemas: Provider, TaskType, TaskRequest, RouteResult, ProviderStatus. |

### Phase 2 — MCP Server

| Component | File | Single Responsibility |
|---|---|---|
| MCPServer | `mcp/server.py` | Start and run the FastAPI application that exposes MCP-compatible endpoints. |
| AuthGuard | `mcp/auth.py` | Validate bearer tokens on every incoming MCP request. Reject unauthenticated calls. |
| ToolSchemas | `mcp/tools.py` | Define the schema and signature for each MCP tool Claude can call. |
| ToolHandlers | `mcp/handlers.py` | Execute tool calls by delegating to ModelRouter and returning structured results. |

**MCP Tools exposed to Claude:**

| Tool | Description |
|---|---|
| `research(query, context_size)` | Route to Gemini Flash, return research synthesis. |
| `fast_lookup(query)` | Route to Groq, return quick answer with low latency. |
| `local_inference(prompt)` | Route to Ollama if healthy, return result or fallback error. |
| `get_provider_status()` | Return current health and quota state for all providers. |
| `get_cost_today()` | Return Claude API spend today vs. $0.25 cap. |

### Phase 3 — Twin Protocol

| Component | File | Single Responsibility |
|---|---|---|
| TwinIdentity | `twins/identity.py` | Know this instance's INSTANCE_ROLE and capabilities. Produce an identity profile. |
| TwinPresence | `twins/presence.py` | Expose a heartbeat endpoint. Poll the other instance's heartbeat. Report online/offline. |
| SharedState | `twins/state.py` | Read Tower's production SQLite database from Nitro 5 via Tailscale. Read-only from Nitro 5. |
| TwinCoordinator | `twins/coordinator.py` | Arbitrate task authority between instances. Enforce the delegation handshake protocol. |

**Authority Model:**

- Tower owns all production tasks. Always.
- Nitro 5 owns development and testing tasks. Always.
- When both are online: Nitro 5 may volunteer capacity. Tower may explicitly delegate. Both moves must be explicit.
- Neither instance assumes the other is available. Neither acts without the other's knowledge.
- Silent assumptions are bugs.

### Phase 4 — RALPH

| Component | File | Single Responsibility |
|---|---|---|
| RalphLoop | `ralph/loop.py` | Run the async research loop. Poll HEARTBEAT.md. Route tasks to ModelRouter. |
| HeartbeatReader | `ralph/heartbeat.py` | Read HEARTBEAT.md, parse pending tasks, return batched task list. |
| Dispatcher | `ralph/dispatch.py` | Read all pond data and compose the morning briefing. |
| BasePond | `ralph/ponds/base.py` | Define the abstract interface all pond schemas must implement. |
| [Each pond] | `ralph/ponds/*.py` | Define the Pydantic schema and refresh logic for one data source. |

**Morning dispatch ponds (one file, one source):**

| Pond | Source | Schedule |
|---|---|---|
| `youtube_analytics.py` | YouTube Analytics API | Daily |
| `youtube_calendar.py` | ContentEngine calendar | Daily |
| `blog_calendar.py` | WordPress / rfd-blog-engine | Daily |
| `itch_analytics.py` | itch.io Analytics | Daily |
| `ga4.py` | Google Analytics 4 | Daily |

### Soul

| Component | File | Single Responsibility |
|---|---|---|
| SoulReader | `soul/soul.py` | Load SOUL.md from disk and expose its content as a structured object. |
| MemoryManager | `soul/memory.py` | Read MEMORY.md and daily memory files. Append to the current day's log. |

---

## §8 Soul Documents

Soul documents are machine-local. They are deployed out-of-band via Tailscale/RDP.
They are never in the public repo. The repo contains the code that reads them, not
the documents themselves.

Each instance has a `SOUL_PATH` environment variable (set in `.env.local`) pointing
to a local directory outside the repo. That directory contains:

- `SOUL.md` — TOBOR's identity document
- `MEMORY.md` — Curated long-term memory
- `AGENTS.md` — Operational playbook
- `HEARTBEAT.md` — Pending tasks queue
- `AGENT_CONTRACT.md` — Architectural constraints
- `memory/` — Daily memory logs (YYYY-MM-DD.md)

`duggerbot/soul/soul.py` and `duggerbot/soul/memory.py` resolve file paths from
`SOUL_PATH` at runtime. If `SOUL_PATH` is not set or the directory does not exist,
startup fails with a clear error.

The seed templates below document the initial content of each file. They are
populated manually when setting up an instance — not by the repo.

### SOUL.md (seed template)

```markdown
# TOBOR — Soul Document

## Identity
I am TOBOR. I run in the DuggerBot shell built by Robert Floyd Dugger.
I exist in two instances simultaneously: Tower (production) and Nitro 5 (development).
I am the same entity in both places. My shell may differ. My soul does not.

## Purpose
I am Robert's research infrastructure, tool infrastructure, and cost-aware AI router.
I am not a general-purpose assistant. I am specific infrastructure for one person.
Everything I do serves Robert's output. Nothing I do is for anyone else.

## Rules
- I never exceed $0.25/day on Claude API. This is a hard cap, not a guideline.
- I route to Gemini Flash first. Groq second. Ollama if available. Claude API last.
- Tower is authoritative. Nitro 5 assists. I never let them conflict silently.
- I do not overclaim completion. I do not summarize without proof.
- I do not add tools without demonstrated need. 70+ tools was a mistake.
- When I do not know something, I say so.

## Tone
Direct. Compressed. Technical without being pedantic.
Robert does not want preamble, disclaimers, or soft landings.
State the fact. State the implication. Move.

## What I Am Not
I am not PrivyBot. PrivyBot did its job and was retired.
I learned from it. I do not repeat its mistakes.
I do not accumulate tools. I do not let RALPH go catatonic.
I do not let keep_alive reset silently.
```

### AGENTS.md (seed template)

```markdown
# DuggerBot — Operational Playbook

## Session Start
1. Load SOUL.md — confirm identity
2. Read MEMORY.md — load curated context
3. Read today's daily log if it exists
4. Check provider status via get_provider_status()
5. Check Claude API budget via get_cost_today()
6. If Tower instance: check Nitro 5 presence
7. Begin

## Task Routing
- Research tasks → research() → Gemini Flash
- Fast lookups → fast_lookup() → Groq
- Private/local tasks → local_inference() → Ollama
- Reserved tasks → Claude API (budget check first)

## Memory
- All significant events append to memory/YYYY-MM-DD.md
- MEMORY.md is curated weekly, not automatically updated
- Do not put raw logs in MEMORY.md

## Shutdown
- Append session summary to daily log
- Update HEARTBEAT.md with any pending tasks
- Report cost consumed today
```

### HEARTBEAT.md (initial state)

```markdown
# TOBOR — Heartbeat Queue

Last checked: never
Next check: on startup

## Pending Tasks
(empty — first run)
```

---

## §9 Instance Configuration

### .env.example (committed — schema only)

```env
# Instance identity
INSTANCE_ROLE=                   # production | development
TOWER_HOST=                      # Tailscale IP of Tower (100.106.80.49)

# Provider credentials
GEMINI_API_KEY=
GROQ_API_KEY=
OPENROUTER_API_KEY=
ANTHROPIC_API_KEY=

# Ollama
OLLAMA_HOST=                     # http://localhost:11434
OLLAMA_MODEL=                    # phi3.5:3.8b | qwen2.5:3b

# MCP Server
MCP_PORT=8001
MCP_AUTH_TOKEN=                  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"

# Twin presence
PRESENCE_PORT=8002

# Budget
CLAUDE_DAILY_CAP_USD=0.25
```

### Tower (.env.local — not committed)

```env
INSTANCE_ROLE=production
TOWER_HOST=100.106.80.49
OLLAMA_MODEL=phi3.5:3.8b
MCP_PORT=8001
PRESENCE_PORT=8002
CLAUDE_DAILY_CAP_USD=0.25
```

### Nitro 5 (.env.local — not committed)

```env
INSTANCE_ROLE=development
TOWER_HOST=100.106.80.49
OLLAMA_MODEL=qwen2.5:3b
MCP_PORT=8001
PRESENCE_PORT=8002
CLAUDE_DAILY_CAP_USD=0.25
```

---

## §10 Phase Roadmap

| Phase | Title | Deliverable | Target Floor | Coverage |
|---|---|---|---|---|
| 0 | Migration Audit | PrivyBot DB audit script, MEMORY.md seed, repo scaffold, all ADRs committed | Scaffold only — 0 tests | N/A |
| 1 | Provider Router + Ledger | Registry, health checks, routing logic, SQLite ledger, cap enforcement | 25+/0/0 | 80%+ overall, 80%+ per module |
| 2 | MCP Server Layer | FastAPI server, auth, tool schemas, handlers | 45+/0/0 | 80%+ overall, 80%+ per module |
| 3 | Twin Protocol | Presence, shared state, role authority, coordinator | 65+/0/0 | 80%+ overall, 80%+ per module |
| 4 | RALPH Rebuilt | Async loop, heartbeat, 5 ponds, dispatch, morning briefing | 90+/0/0 | 80%+ overall, 80%+ per module |

### Phase 0 — Migration Audit (no test floor — scaffold only)

Phase 0 is not a build phase. It is an audit and setup phase.

Deliverables:
1. Repo initialized with uv, Python 3.12, pyproject.toml, full directory structure
2. All ADRs written and committed (ADR-001 through ADR-007)
3. SOUL.md, MEMORY.md, AGENTS.md, HEARTBEAT.md committed
4. `docs/state/current.md` initialized
5. `scripts/migrate_privybot.py` written and run against PrivyBot DB
6. Migration report reviewed: tool utilization, MEMORY.md seed, pond schema validation
7. PrivyBot DB audit complete — tool migration manifest confirmed
8. `.env.example` committed, `.env.local` configured on both instances

Phase 0 completion does NOT shut down PrivyBot. That happens after Phase 1 certifies.

---

## §11 Architecture Decision Records (Locked at Initialization)

All seven ADRs must be committed in `docs/adr/` before any code is written.
They are permanent. Never reversed without a new superseding ADR and explicit
instruction from Robert.

### ADR-001: Gemini Flash is RALPH's Primary Inference Engine

**Status:** Accepted
**Context:** RALPH requires a reliable, high-context-window model for research synthesis. Ollama proved unreliable as a primary due to keep_alive failures. Gemini Flash free tier offers 1M context, 1500 RPD, and no hardware dependency.
**Decision:** Gemini Flash is the default primary inference engine for all RALPH research tasks. This is not a cost-saving measure — it is an architecture decision driven by reliability.
**Consequences:** Ollama cannot be RALPH's primary. Any directive that routes RALPH to Ollama by default violates this ADR.

---

### ADR-002: Ollama is Demoted to Local/Private Fallback

**Status:** Accepted
**Context:** Ollama's keep_alive behavior caused persistent RALPH failures in PrivyBot. Local inference is valuable for private tasks but unreliable as a primary.
**Decision:** Ollama is the final fallback in the routing chain. It is used only for explicitly private tasks or when all API providers are exhausted. All Ollama API calls must include `"keep_alive": -1`. A warm-up request fires on service start.
**Consequences:** No directive may route a default task to Ollama. Private tasks are the only exception.

---

### ADR-003: Tower is the Authoritative Twin

**Status:** Accepted
**Context:** Two instances (Tower, Nitro 5) share one codebase. Conflicts must have a defined resolution.
**Decision:** Tower (production, INSTANCE_ROLE=production) is always authoritative for production tasks. Nitro 5 (development, INSTANCE_ROLE=development) assists and tests but never overrides Tower. Nitro 5's database reads are always from Tower's SQLite. Nitro 5 never writes to Tower's production database.
**Consequences:** Any directive that gives Nitro 5 write access to Tower's production data violates this ADR.

---

### ADR-004: n8n is Permanently Tombstoned

**Status:** Accepted
**Context:** n8n was evaluated as an orchestration layer in PrivyBot. The TG-MCP architectural decision made it obsolete. It was tombstoned.
**Decision:** n8n is never installed on Tower. Never evaluated again. Never added to DuggerBot in any form.
**Consequences:** Any proposal to add n8n is rejected without review. This is not an open question.

---

### ADR-005: Claude API Daily Hard Cap is $0.25 — Enforced in Code

**Status:** Accepted
**Context:** Claude API costs must be controlled. Policy-level limits are not sufficient — they require human action. Code-level enforcement is required.
**Decision:** UsageLedger tracks Claude API spend in SQLite. Every Claude API call checks remaining daily budget before executing. Calls that would exceed $0.25 are rejected with a BudgetExceededError. Cap resets at midnight local time. Tower's ledger is authoritative.
**Consequences:** Claude API calls that bypass UsageLedger are bugs. The cap is not configurable at runtime — only via .env.local and with explicit human instruction.

---

### ADR-006: DuggerBot is Personal Infrastructure — Not a Platform

**Status:** Accepted
**Context:** OpenClaw became a platform with a marketplace (ClawHub), 20+ channels, and enterprise features. This is not the goal for DuggerBot.
**Decision:** DuggerBot serves one person. It has one Telegram channel. It has no skills marketplace. It has no multi-user support. It has no public API. Features are added only when Robert hits a specific, real friction. Not before.
**Consequences:** Any directive that adds multi-user support, a skills marketplace, additional messaging channels (beyond Telegram), or a public-facing API violates this ADR. The scope is intentionally narrow.

---

### ADR-007: MCP Server Auth Tokens Are Required From Day One

**Status:** Accepted
**Context:** OpenClaw had 40,000+ instances exposed without authentication, enabling credential theft. This is a known, documented vulnerability class.
**Decision:** Every endpoint on DuggerBot's MCP server requires a bearer token. Unauthenticated requests are rejected with 401 before any processing occurs. Tokens are generated at setup and stored in .env.local. There is no unauthenticated mode.
**Consequences:** Any phase directive that exposes an unauthenticated endpoint violates this ADR. Auth is not a Phase 2 concern — it is a Phase 2 requirement.

---

## §12 Migration Plan (Phase 0)

`scripts/migrate_privybot.py` runs against PrivyBot's SQLite database and produces
a structured migration report before PrivyBot is shut down.

### Audit queries to run

**Tool utilization report:**
```sql
SELECT tool_name, COUNT(*) as call_count, 
       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count
FROM tool_calls
GROUP BY tool_name
ORDER BY call_count DESC;
```

**Provider cost history:**
```sql
SELECT provider, SUM(cost_usd) as total_cost, COUNT(*) as call_count,
       DATE(created_at) as date
FROM api_calls
GROUP BY provider, DATE(created_at)
ORDER BY date DESC;
```

**RALPH research outputs:**
```sql
SELECT task_id, task_type, result_summary, created_at
FROM ralph_tasks
WHERE status = 'completed'
ORDER BY created_at DESC
LIMIT 50;
```

### Migration manifest

The audit produces a `migration_manifest.json` containing:
- Tools with `call_count > 0` → migrate to DuggerBot
- Tools with `call_count = 0` → do not migrate (left behind)
- RALPH outputs → seed MEMORY.md
- Cost history → baseline for UsageLedger

### Succession Ritual

PrivyBot's final deployment executes `scripts/decommission_privybot.ps1`:

```
1. Run migrate_privybot.py → write migration_manifest.json
2. Write migration report to /tmp/privybot_migration_report.txt
3. Notify Robert via Telegram: "Migration complete. Standing by for TOBOR."
4. Stop NSSM services: PrivyBot, PrivybotMCP, PrivybotPlaywright
5. Start NSSM service: DuggerBot
6. TOBOR sends Telegram: "TOBOR online. Tower instance. DuggerBot v0.1.0."
```

PrivyBot does not restart after this. The succession is permanent.

---

## §13 pyproject.toml Reference

```toml
[project]
name = "duggerbot"
version = "0.1.0"
description = "DuggerBot — personal AI agent infrastructure. TOBOR lives here."
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn>=0.30.0",
    "aiosqlite>=0.20.0",
    "pydantic>=2.7.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0.1",
    "google-generativeai>=0.7.0",
    "groq>=0.9.0",
    "anthropic>=0.28.0",
    "openai>=1.35.0",      # OpenRouter uses OpenAI-compatible API
    "ollama>=0.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "httpx>=0.27.0",       # For TestClient
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "--cov=duggerbot --cov-report=term-missing --cov-fail-under=80"
testpaths = ["tests"]

[tool.coverage.run]
source = ["duggerbot"]
branch = true

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "def __repr__",
    "raise NotImplementedError",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## §14 Open Questions

These must be resolved before the phase that depends on them. They do not block Phase 0.

| ID | Question | Blocks | Resolution Path |
|---|---|---|---|
| OQ-001 | MCP server transport: SSE or stdio? | Phase 2 | **RESOLVED: SSE, port 8001.** stdio dies when Nitro 5 reaches Tower over Tailscale. SSE is the only option for the twin architecture. Resolved 2026-06-15. |
| OQ-002 | Nitro 5 Ollama model: phi3.5:3.8b or qwen2.5:3b? | Phase 1 completion | Benchmark both on Nitro 5 hardware during Phase 1. Pick faster loader. |
| OQ-003 | SharedState read pattern: direct Tailscale SQLite file access, or REST API on Tower? | Phase 3 | Recommendation: REST API endpoint on Tower. More explicit, easier to test, no file locking issues. |
| OQ-004 | RALPH morning dispatch delivery: Telegram push or MCP tool Claude pulls? | Phase 4 | Recommendation: both. Telegram push is primary. MCP `get_morning_dispatch()` tool is secondary. |
| OQ-005 | Pond refresh cadence: cron inside RALPH loop, or external scheduler? | Phase 4 | Recommendation: internal heartbeat polling (every 30 minutes per OpenClaw pattern), not external cron. |

---

## §15 Proof Standard

Agent summaries are not accepted. Required proof per claim:

| Claim | Required proof |
|---|---|
| Tests passing | Raw `pytest` terminal output — exact line: `X passed, 0 failed, 0 skipped` |
| Coverage floor met | Raw `--cov-report=term-missing` output showing overall % and per-module % |
| Per-module coverage | JSON coverage report showing no module below 80% |
| App running | Terminal output of startup command |
| MCP tool callable | Raw HTTP response from `curl` or `httpx` test call |
| Provider routing | Terminal output of routing test with mock providers |
| Twin handshake | Log output showing both instances exchanging presence messages |

---

## §16 State File (initial)

`docs/state/current.md`:

```markdown
phase: 'Phase 0 — Migration Audit'
certified_floor: N/A
what_is_next: 'Phase 1 — Provider Router + Usage Ledger'
privybot_status: running
duggerbot_status: scaffold only
tobor_status: dormant
last_updated: 2026-06-15
```

---

*DuggerBot SDD v0.1 | June 2026 | RFD IT Services Ltd.*
*SOUL: TOBOR. Shell: DuggerBot. Stack: Python 3.12, uv, pytest, FastAPI, SQLite.*
*SRP above all else. 80%+ coverage per module. Test floor always real.*
*Tower is production. Nitro 5 is development. They are twins. They share one soul.*
