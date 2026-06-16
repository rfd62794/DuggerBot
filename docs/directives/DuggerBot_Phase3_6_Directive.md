# DuggerBot — Phase 3.6 Directive: Version Tracking and Self-Update

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run `uv run pytest` before touching any file.
> Must report **174 passed, 0 failed, 0 skipped** (Phase 3.5 certified floor).
> If count differs, stop and report — do not proceed.

---

## §0 Context

Phase 3.5 delivered the developer tools tether — certified at 174/0/0.

Phase 3.6 delivers **version tracking and the self-update protocol** defined in
ADR-009. When complete, DuggerBot knows its own version, can detect when a newer
version is available on `origin/main`, can pull and restart itself via NSSM exit
codes, can notify its twin to do the same, and the `get_version()` dev tool lets
Claude ask TOBOR what revision it is without Robert intermediating.

Phase 3.6 also delivers `scripts/initialize.ps1` — the Initializer that must
exist before DuggerBot can be deployed to a fresh instance (Tower or Nitro 5).
Without it, deployment is manual every time.

**What Phase 3.6 produces:**
- `duggerbot/version.py` — version string, revision computation, update check, pull
- Two new dev tools: `get_version()` and `check_for_update()`
- Background update check coroutine in server lifespan
- `/health` endpoint updated to include version string
- `POST /twin/upgrade` wired to actual update logic (was a stub in Phase 3)
- `scripts/initialize.ps1` — Initializer script (no unit tests — manual verification)
- 21 new tests, 0 failures, 0 skipped

**What Phase 3.6 does NOT produce:**
- RALPH or any Phase 4 work
- Telegram bot integration
- Automatic push to Tower from Nitro 5 — the twin notification is advisory only

**Critical design note — subprocess in version.py:**
`version.py` uses `subprocess.run` (blocking), not `asyncio.create_subprocess_exec`.
This is intentional. The update workflow is sequential: check → defer if needed →
pull → exit. It is not called from a hot path. Do not async-ify it.

**Critical design note — exit from async context:**
Update-triggered restarts use `os._exit(0)` for success and `os._exit(1)` for
failure. `sys.exit()` raises `SystemExit` which FastAPI/uvicorn may swallow.
`os._exit()` bypasses Python cleanup handlers — aiosqlite connections do not close
cleanly. SQLite ACID guarantees prevent corruption. WAL files may linger but clean
up on next open. This is acceptable for a service restart. Do not change to
`sys.exit()`.

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/version.py` | New | Version string, revision computation, update check, pull |
| `duggerbot/mcp/dev_tools.py` | Modify | Add `handle_get_version()` and `handle_check_for_update()` |
| `duggerbot/mcp/tools.py` | Modify | Add 2 new schemas to `get_dev_tool_list()` |
| `duggerbot/mcp/server.py` | Modify | Background update coroutine, version in /health, wire upgrade |
| `duggerbot/twins/router.py` | Modify | Wire `POST /twin/upgrade` to version module (was stub) |
| `.env.example` | Modify | Add `UPDATE_CHECK_INTERVAL_MINUTES`, `UPDATE_CHECK_RETRY_MINUTES` |
| `config/instance.yaml` | Modify | Add the two new env var schemas |
| `scripts/initialize.ps1` | New | Initializer — no unit tests, manual verification on Nitro 5 first |
| `tests/test_version.py` | New | 10 tests |
| `tests/mcp/test_dev_tools.py` | Modify | 4 new tests |
| `tests/mcp/test_tools.py` | Modify | 2 new tool schema tests |
| `tests/mcp/test_server.py` | Modify | 3 new tests |
| `tests/twins/test_router.py` | Modify | 2 new tests |
| `docs/state/current.md` | Modify | Update as final step only |

**Read-only — do not touch:**
All `duggerbot/router/`, `duggerbot/twins/` except `router.py`,
`duggerbot/ralph/`, `duggerbot/soul/`, all `docs/adr/`,
soul documents, `.gitignore`, `config/providers.yaml`, `config/routing.yaml`,
all test files in `tests/router/` and `tests/twins/` except `test_router.py`

---

## §2 Implementation

---

### 2.1 `.env.example` additions

```env
# Self-update
UPDATE_CHECK_INTERVAL_MINUTES=60   # How often to check for updates (background)
UPDATE_CHECK_RETRY_MINUTES=5       # Retry delay when deferred due to in-flight work
```

---

### 2.2 `duggerbot/version.py` (NEW)

> ⚠️ **RULE:** version.py uses `subprocess.run` only — never async subprocess.
> Every function in this file is synchronous. Callers handle async scheduling.

> ⚠️ **RULE:** `pull_update()` returns bool. It never raises. Callers decide
> what to do with False (which is always `os._exit(1)`).

```python
import os
import subprocess
from pathlib import Path

# Semantic version — bump these manually on breaking changes
MAJOR = 0
MINOR = 1
PATCH = 0


def _run_git(*args: str) -> tuple[int, str]:
    """Run a git command. Returns (returncode, stdout.strip())."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,  # repo root
    )
    return result.returncode, result.stdout.strip()


def get_revision() -> int:
    """Return git commit count on HEAD. Returns 0 if git unavailable."""
    code, out = _run_git("rev-list", "--count", "HEAD")
    return int(out) if code == 0 and out.isdigit() else 0


def get_remote_revision() -> int:
    """
    Fetch from origin and return remote commit count on main.
    Returns 0 if fetch fails or git unavailable.
    Performs a network call (git fetch) — do not call from hot paths.
    """
    _run_git("fetch", "origin", "main")
    code, out = _run_git("rev-list", "--count", "origin/main")
    return int(out) if code == 0 and out.isdigit() else 0


def get_version_string() -> str:
    """Return full version string: MAJOR.MINOR.PATCH.rN"""
    return f"{MAJOR}.{MINOR}.{PATCH}.r{get_revision()}"


def get_git_hash() -> str:
    """Return short git commit hash for debugging. Returns 'unknown' on failure."""
    code, out = _run_git("rev-parse", "--short", "HEAD")
    return out if code == 0 else "unknown"


def is_update_available() -> bool:
    """
    True if origin/main has more commits than local HEAD.
    Performs git fetch — network call, may be slow.
    """
    remote = get_remote_revision()
    local = get_revision()
    return remote > local and remote > 0


def pull_update() -> bool:
    """
    Run git pull origin main.
    Returns True on success, False on any failure.
    Does NOT exit — caller decides exit code.
    """
    code, _ = _run_git("pull", "origin", "main")
    return code == 0


def apply_update_and_exit() -> None:
    """
    Pull and exit with appropriate code for NSSM recovery:
    - Exit 0: pull succeeded → NSSM will restart with new version
    - Exit 1: pull failed → NSSM will stop (no restart loop)
    Uses os._exit() — bypasses Python cleanup. Intentional per ADR-009.
    """
    if pull_update():
        os._exit(0)
    else:
        os._exit(1)
```

---

### 2.3 `duggerbot/mcp/dev_tools.py` modifications

Add two new handlers. Add both to `DEV_TOOL_HANDLERS`.

```python
async def handle_get_version(arguments: dict) -> list[TextContent]:
    """
    Return current version string, revision, git hash, and instance role.
    Fast — no network call, no git fetch.
    """
    from duggerbot.version import get_version_string, get_revision, get_git_hash
    import os
    return [TextContent(type="text", text=json.dumps({
        "version": get_version_string(),
        "revision": get_revision(),
        "git_hash": get_git_hash(),
        "instance_role": os.environ.get("INSTANCE_ROLE", "unknown"),
        "error": None,
    }))]


async def handle_check_for_update(arguments: dict) -> list[TextContent]:
    """
    Check if a newer version is available on origin/main.
    Slow — performs git fetch. Returns local vs remote revision comparison.
    """
    from duggerbot.version import get_revision, get_remote_revision
    import asyncio
    loop = asyncio.get_event_loop()
    # Run in thread pool — subprocess.run is blocking
    local = await loop.run_in_executor(None, get_revision)
    remote = await loop.run_in_executor(None, get_remote_revision)
    return [TextContent(type="text", text=json.dumps({
        "local_revision": local,
        "remote_revision": remote,
        "update_available": remote > local and remote > 0,
        "error": None,
    }))]
```

> ⚠️ **RULE:** `handle_check_for_update` runs `get_remote_revision()` in a
> thread pool via `loop.run_in_executor`. `subprocess.run` is blocking and must
> not run on the event loop thread. This is the correct pattern for blocking
> calls from async handlers.

---

### 2.4 `duggerbot/mcp/tools.py` modifications

Add two schemas to `get_dev_tool_list()`:

| Tool | Params | Description |
|---|---|---|
| `get_version` | none | Returns version string, revision, git hash, instance role — no network |
| `check_for_update` | none | Fetches from origin, returns local vs remote revision comparison — slow |

---

### 2.5 `duggerbot/mcp/server.py` modifications

**Three changes — no others:**

**1. Update `/health` response to include version:**
```python
# In health_endpoint():
from duggerbot.version import get_version_string
return {
    "status": "ok",
    "name": TOBOR_IDENTITY,
    "version": get_version_string(),      # ADD THIS
    "instance": os.environ.get("INSTANCE_ROLE", "unknown"),
    "providers": len(app.state.registry.list_enabled()) if hasattr(app.state, "registry") else 0,
}
```

**2. Background update check coroutine in lifespan:**
```python
async def _update_check_loop(app: FastAPI) -> None:
    """
    Background task: periodically check for updates.
    Defers if TwinCoordinator has in-flight delegation.
    Applies update and exits if update available and clear.
    """
    import os
    from duggerbot.version import is_update_available, apply_update_and_exit
    interval = int(os.environ.get("UPDATE_CHECK_INTERVAL_MINUTES", "60")) * 60
    retry = int(os.environ.get("UPDATE_CHECK_RETRY_MINUTES", "5")) * 60

    while True:
        await asyncio.sleep(interval)
        try:
            if not is_update_available():
                continue
            # Check coordinator for in-flight work
            coordinator: TwinCoordinator = app.state.coordinator
            if await coordinator.has_inflight_work():
                await asyncio.sleep(retry)
                continue
            # Clear to update — this call does not return
            apply_update_and_exit()
        except Exception:
            # Never let the update check crash the server
            pass
```

Start in lifespan:
```python
task = asyncio.create_task(_update_check_loop(app))
yield
task.cancel()
```

**3. Wire dev tools in `call_tool` — already done in Phase 3.5, confirm no change needed.**

> ⚠️ **RULE:** These are the only three changes to server.py in Phase 3.6.
> Do not touch the SSE endpoint, auth wiring, or MCP server registration.

---

### 2.6 `duggerbot/twins/coordinator.py` modification

Add `has_inflight_work()` method — the update check uses this.

```python
async def has_inflight_work(self) -> bool:
    """
    Returns True if this instance currently has an in-flight delegation.
    Phase 4 will extend this to also check active RALPH cycles.
    """
    return self._inflight_delegation_count > 0
```

Add `_inflight_delegation_count: int = 0` to `__init__`.
Increment when `delegate_to_remote()` starts, decrement when it returns.

> ⚠️ **RULE:** This is the only permitted change to coordinator.py.
> No other coordinator logic changes in this phase.

---

### 2.7 `duggerbot/twins/router.py` modification

Wire `POST /twin/upgrade` to actual logic. In Phase 3 it was a stub.

```python
@twin_router.post("/upgrade", dependencies=[Depends(verify_token)])
async def request_upgrade(request: Request) -> dict:
    """
    Advisory upgrade request from the other twin.
    Checks coordinator for in-flight work, then checks for update.
    Returns decision without performing the update synchronously —
    the update coroutine will handle it on next check cycle.
    """
    coordinator: TwinCoordinator = request.app.state.coordinator
    if await coordinator.has_inflight_work():
        retry = int(os.environ.get("UPDATE_CHECK_RETRY_MINUTES", "5"))
        return {
            "accepted": False,
            "reason": "in-flight delegation active",
            "retry_after_minutes": retry,
        }
    from duggerbot.version import is_update_available
    import asyncio
    loop = asyncio.get_event_loop()
    update_available = await loop.run_in_executor(None, is_update_available)
    if not update_available:
        return {"accepted": False, "reason": "already at latest revision"}
    return {
        "accepted": True,
        "reason": "update will apply on next check cycle",
        "retry_after_minutes": 1,
    }
```

---

### 2.8 `scripts/initialize.ps1` (NEW — no unit tests)

> ⚠️ **RULE:** Test this on Nitro 5 first. Do not run on Tower until Nitro 5
> validates that the script correctly sets up NSSM and the service starts.
> The script is idempotent — safe to re-run on an existing installation.

```powershell
<#
.SYNOPSIS
    DuggerBot Initializer — first-time setup and NSSM service registration.
    Idempotent: safe to run on existing installations.
    Test on Nitro 5 before running on Tower.

.PARAMETER RepoPath
    Path to DuggerBot repo. Default: C:\Github\DuggerBot

.PARAMETER ServiceName
    NSSM service name. Default: DuggerBot

.PARAMETER PythonPath
    Path to uv executable. Default: auto-detected from PATH.
#>
param(
    [string]$RepoPath = "C:\Github\DuggerBot",
    [string]$ServiceName = "DuggerBot",
    [string]$PythonPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "→ $msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

# 1. Verify prerequisites
Write-Step "Checking prerequisites"
foreach ($cmd in @("git", "uv", "nssm")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Fail "$cmd not found in PATH. Install it and re-run."
    }
    Write-OK "$cmd found"
}

# 2. Clone or pull repo
Write-Step "Updating repo at $RepoPath"
if (-not (Test-Path $RepoPath)) {
    git clone https://github.com/rfd62794/DuggerBot.git $RepoPath
    Write-OK "Cloned"
} else {
    Set-Location $RepoPath
    git pull origin main
    Write-OK "Pulled"
}
Set-Location $RepoPath

# 3. Install dependencies
Write-Step "Installing dependencies"
uv sync
Write-OK "Dependencies installed"

# 4. Check .env.local
Write-Step "Checking .env.local"
if (-not (Test-Path "$RepoPath\.env.local")) {
    Write-Host "  .env.local not found. Copy .env.example and fill in values:" -ForegroundColor Yellow
    Write-Host "  $RepoPath\.env.example" -ForegroundColor Yellow
    Write-Fail "Create .env.local and re-run."
}
Write-OK ".env.local present"

# 5. SOUL_PATH reminder
Write-Host ""
Write-Host "  REMINDER: Soul documents must be placed at the path in SOUL_PATH" -ForegroundColor Yellow
Write-Host "  Copy via Tailscale or RDP — they are not in the repo." -ForegroundColor Yellow
Write-Host ""

# 6. Register or update NSSM service
Write-Step "Configuring NSSM service: $ServiceName"
$uvExe = if ($PythonPath) { $PythonPath } else { (Get-Command uv).Source }
$startCmd = "$uvExe run python -m duggerbot.main"

$existing = nssm status $ServiceName 2>&1
if ($LASTEXITCODE -ne 0) {
    # Service doesn't exist — create it
    nssm install $ServiceName $uvExe
    Write-OK "Service installed"
} else {
    Write-OK "Service exists — updating config"
    nssm stop $ServiceName 2>$null
}

# Apply prescriptive config per ADR-009
nssm set $ServiceName Application $uvExe
nssm set $ServiceName AppParameters "run python -m duggerbot.main"
nssm set $ServiceName AppDirectory $RepoPath
nssm set $ServiceName AppEnvironmentExtra "PYTHONUNBUFFERED=1"
nssm set $ServiceName AppExit default Restart    # Exit 0 → restart (clean update)
nssm set $ServiceName AppExit 1 Stop             # Exit 1 → stop (error, no loop)
nssm set $ServiceName AppRestartDelay 5000       # 5s delay before restart
nssm set $ServiceName AppThrottle 10000          # Throttle rapid restarts
nssm set $ServiceName AppStopMethodConsole 1500  # Graceful shutdown window
nssm set $ServiceName AppStopMethodWindow 1500
nssm set $ServiceName AppStopMethodThreads 1500
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName ObjectName LocalSystem

Write-OK "NSSM config applied (ADR-009 prescriptive settings)"

# 7. Start service
Write-Step "Starting $ServiceName"
nssm start $ServiceName
Start-Sleep -Seconds 3

# 8. Verify /health
Write-Step "Verifying service health"
$port = (Get-Content "$RepoPath\.env.local" | Select-String "MCP_PORT").ToString().Split("=")[1].Trim()
if (-not $port) { $port = "8001" }

$attempts = 0
$maxAttempts = 10
while ($attempts -lt $maxAttempts) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:$port/health" -TimeoutSec 3
        Write-OK "Health check passed: $($response.version)"
        break
    } catch {
        $attempts++
        if ($attempts -eq $maxAttempts) {
            Write-Fail "Service did not respond at /health after 30 seconds. Check nssm logs."
        }
        Start-Sleep -Seconds 3
    }
}

Write-Host ""
Write-Host "DuggerBot initialized successfully." -ForegroundColor Green
Write-Host "Version: $(Invoke-RestMethod -Uri "http://localhost:$port/health" | Select-Object -ExpandProperty version)" -ForegroundColor Green
```

---

## §3 Test Anchors

All subprocess calls in `version.py` are mocked via `pytest-mock`.
`os._exit()` must be mocked — never call real exit in tests.
`get_remote_revision()` must be mocked — never perform real network calls.

Target: **21 new tests**
Full suite target: **≥195 passed, 0 failed, 0 skipped**

---

### `tests/test_version.py` — 10 tests

| Test | Behaviour |
|---|---|
| `test_get_revision_returns_int` | Mocked git → returns integer |
| `test_get_revision_returns_zero_on_git_failure` | git fails → returns 0 |
| `test_get_version_string_format` | Returns "0.1.0.rN" pattern |
| `test_get_version_string_contains_revision` | Revision N matches get_revision() |
| `test_get_git_hash_returns_string` | Mocked git → returns string |
| `test_get_git_hash_returns_unknown_on_failure` | git fails → "unknown" |
| `test_is_update_available_true_when_remote_ahead` | remote > local → True |
| `test_is_update_available_false_when_current` | remote == local → False |
| `test_pull_update_returns_true_on_success` | git pull exit 0 → True |
| `test_pull_update_returns_false_on_failure` | git pull exit 1 → False |

---

### `tests/mcp/test_dev_tools.py` additions — 4 tests

| Test | Behaviour |
|---|---|
| `test_get_version_returns_version_string` | Response JSON has "version" key matching format |
| `test_get_version_returns_instance_role` | Response JSON has "instance_role" from env |
| `test_check_for_update_returns_local_and_remote` | Response has local_revision, remote_revision |
| `test_check_for_update_update_available_true` | remote > local → update_available True |

---

### `tests/mcp/test_tools.py` additions — 2 tests

| Test | Behaviour |
|---|---|
| `test_get_version_schema_valid` | Schema has name, description, empty required |
| `test_check_for_update_schema_valid` | Schema has name, description, empty required |

---

### `tests/mcp/test_server.py` additions — 3 tests

| Test | Behaviour |
|---|---|
| `test_health_response_includes_version` | GET /health → JSON has "version" key |
| `test_health_version_matches_format` | version field matches `\d+\.\d+\.\d+\.r\d+` |
| `test_update_check_defers_when_inflight` | coordinator.has_inflight_work() True → no exit |

---

### `tests/twins/test_router.py` additions — 2 tests

| Test | Behaviour |
|---|---|
| `test_upgrade_endpoint_defers_when_inflight` | has_inflight_work True → accepted False |
| `test_upgrade_endpoint_accepts_when_update_available` | no inflight + update available → accepted True |

---

## §4 Completion Criteria

- [ ] `uv run pytest tests/test_version.py` reports **10 passed, 0 failed, 0 skipped**
- [ ] Full suite: **≥195 passed, 0 failed, 0 skipped**
- [ ] `--cov=duggerbot/version --cov-fail-under=80` passes
- [ ] `version.py` ≥ 80% coverage
- [ ] `os._exit()` used in `apply_update_and_exit()` — confirm by reading file
- [ ] `subprocess.run` used in `version.py` (not async subprocess) — confirm by reading
- [ ] `get_remote_revision()` uses `run_in_executor` in `handle_check_for_update` — confirm
- [ ] `coordinator.has_inflight_work()` implemented and used in update check loop
- [ ] `/health` response includes `version` field (manual: `curl localhost:8001/health`)
- [ ] `POST /twin/upgrade` returns `accepted: false` when in-flight (test-enforced)
- [ ] `scripts/initialize.ps1` exists, readable, NSSM config matches ADR-009 values
- [ ] `initialize.ps1` manually tested on Nitro 5 before running on Tower
- [ ] Dev tool list has 7 tools total (5 original + get_version + check_for_update)
- [ ] ISSUE-001 still open — confirm no regression
- [ ] `docs/state/current.md` updated

**Proof required:**
```
Full pytest output: exact line showing "X passed, 0 failed, 0 skipped"
Coverage output: version.py line from --cov-report=term-missing
curl /health output: raw JSON showing version field
```

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 3.6 — Version Tracking and Self-Update |
| Pre-flight | 174/0/0 (Phase 3.5 certified) |
| New tests | 21 |
| Full suite target | ≥195/0/0 |
| Version format | `MAJOR.MINOR.PATCH.rN` — N from `git rev-list --count HEAD` |
| Exit codes | 0 = restart (clean update), 1 = stop (error, no loop) |
| Exit mechanism | `os._exit()` — not `sys.exit()` — intentional per ADR-009 |
| subprocess in version.py | `subprocess.run` (blocking) — not async — intentional |
| check_for_update handler | `run_in_executor` wraps blocking git call — mandatory |
| NSSM prescriptive config | In initialize.ps1 and ADR-009 — `AppExit 1 Stop` is critical |
| Initialize order | Nitro 5 first, Tower second — never reverse |
| has_inflight_work() | New coordinator method — update check and /twin/upgrade both use it |
| Soul documents | NOT copied by Initializer — operator handles via Tailscale/RDP |
| New dev tools | get_version (fast), check_for_update (slow, network) |
| Total dev tools | 7 (was 5 after Phase 3.5) |
| Open issues | ISSUE-001 (router.py coverage, close before Phase 4) |
| Read-only | router/, ralph/, soul/, all ADRs, soul documents, config YAMLs |
| Next phase | Phase 4 — RALPH Rebuilt |
