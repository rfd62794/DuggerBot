# ISSUE-001: router.py Coverage Debt (91% → 80%+ floor)

**Status:** Open
**Severity:** Low — above 80% floor, no functional gap
**Filed:** 2026-06-15
**Blocks:** Nothing. Must close before Phase 4 (RALPH under full load).

---

## Description

`duggerbot/router/router.py` is at 91% coverage after Phase 1 certification.
The missing 9% represents real code paths that are not exercised by the current
35-test suite:

| Lines | Branch | What's uncovered |
|---|---|---|
| 49 | `provider is None or not provider.enabled` | Disabled provider appearing in routing chain |
| 61–63 | `except BudgetExceededError` | Budget exceeded catch inside routing loop (tested indirectly via `test_claude_budget_exceeded_skipped` but branch coverage tool marks partial) |
| 88→91 | `require_local` fallback | `require_local=True` when `local_inference` override is missing from `routing.yaml` |

## Acceptance Criteria

- [ ] Add test: disabled provider in chain is silently skipped
- [ ] Add test: `require_local=True` with no `local_inference` override falls back to `default_chain`
- [ ] Verify `router.py` branch coverage ≥ 95% after fixes
- [ ] No new modules, no new dependencies

## Context

Phase 1 certified at 97% overall, all modules ≥80%. This issue tracks the
remaining debt on the one module below 95%. Not urgent — router is only called
by MCP handlers (Phase 2) and RALPH (Phase 4). Close before Phase 4 directive.
