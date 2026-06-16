phase: 'Phase 3.7 — Deployment Gate'
certified_floor: '200 passed, 0 failed, 0 skipped'
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
what_is_next: 'Phase 4 — RALPH Rebuilt'
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
last_updated: 2026-06-16
