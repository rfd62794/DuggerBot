# Pending Decision: Cline CLI Availability

**Phase:** 3.8 — Context Store + Cline Dispatch
**Date:** 2026-06-16
**Status:** BLOCKED — awaiting resolution

## Question

`cline --help` returns "not recognized" on Nitro 5. The Cline CLI is not installed
or not in PATH. The directive requires confirming exact flag syntax before implementing
`dispatch_to_cline`.

## Options

1. **Install Cline CLI** — `npm install -g @anthropics/cline` (or equivalent).
   Then verify `cline --help` output and implement the handler.

2. **Stub the handler** — Implement `handle_dispatch_to_cline` as a placeholder that
   returns `{"error": "Cline CLI not installed", "success": false}`. Add the real
   subprocess call after installation.

3. **Defer dispatch_to_cline** — Ship Phase 3.8 with context store only (4 tools, 9 tests).
   Add Cline dispatch as Phase 3.8b after CLI installation is confirmed.

## Impact

Context store (4 tools) is independent and ready to ship. Only `dispatch_to_cline`
is blocked. The 4 context tools can land now without waiting for this decision.
