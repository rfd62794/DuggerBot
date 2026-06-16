phase: 'Phase 3.9 — HEARTBEAT Reader'
certified_floor: '204 passed, 0 failed, 0 skipped'
coverage_overall: '96% (twins+mcp), 97% (router)'
coverage_per_module:
  # Phase 1 — Provider Router
  models: '100%'
  registry: '100%'
  health: '100%'
  ledger: '100%'
  router: '91%'
  # Phase 2 — MCP Server Layer
  mcp/auth: '100%'
  mcp/handlers: '100%'
  mcp/tools: '100%'
  mcp/server: '87%'
  # Phase 3 — Twin Protocol
  twins/models: '100%'
  twins/identity: '100%'
  twins/presence: '100%'
  twins/router: '100%'
  twins/state: '94%'
  twins/coordinator: '92%'
  # Phase 3.5 — Developer Tools Tether
  mcp/dev_tools: '83%'
  # Phase 3.6 — Version Tracking and Self-Update
  version: '85%'
what_is_next: 'Phase 3.8 — dispatch_to_cline tool (after Part B verification)'
privybot_status: running
duggerbot_status: deployment gate certified — Part A (code) and Part B (manual verification) complete
tobor_status: running — 0.1.0.r50, development instance, Nitro 5
oq_001: 'RESOLVED — SSE, port 8001'
oq_003: 'RESOLVED — REST API on Tower for shared state'
issue_001: 'OPEN — router.py coverage debt (91%) — close before Phase 4'
issue_002: 'RESOLVED — CallerIdentity in auth.py, Devin routing restriction'
issue_003: 'OPEN — task_source Phase 1 model touch'
issue_004: 'RESOLVED — deployment scripts gitignored, fixed with negation rules'
issue_005: 'OPEN — NSSM PATH missing git/uv, version reads r0 — low priority'
issue_006: 'OPEN — NSSM git fetch auth fails as LocalSystem — blocks self-update'
adr_010: 'Accepted — Six-level agent hierarchy, Cline as Level 3'
clinerules: 'present — repo governance for Cline sessions'
last_updated: 2026-06-16
