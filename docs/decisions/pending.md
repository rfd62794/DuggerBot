# Decision: Cline CLI Availability — RESOLVED

**Phase:** 3.8.1 — Cline Dispatch Live
**Date:** 2026-06-16
**Status:** RESOLVED — Option 1 chosen

## Resolution

Cline CLI 3.0.24 installed. `dispatch_to_cline` implemented with confirmed syntax:

```bash
cline "<task>" --provider ollama --model <model> --auto-approve true \
  --cwd <repo_root> --timeout <seconds> --json
```

Handler uses `asyncio.create_subprocess_exec` with timeout (default 300s,
configurable via `CLINE_TIMEOUT_SECONDS`).

## Decision Record

- **Option 1 selected:** Install Cline CLI and implement full handler
- **Implementation:** `duggerbot/mcp/dev_tools.py:handle_dispatch_to_cline`
- **Tests:** `tests/mcp/test_dev_tools.py:test_handle_dispatch_to_cline_returns_output`
- **Phase:** 3.8.1 complete — 216/0/0
