# DuggerBot — Phase 3.5 Directive: Developer Tools Tether

*June 2026 | Read fully before executing anything.*

---

> ⛔ **STOP:** Run `uv run pytest` before touching any file.
> Must report **149 passed, 0 failed, 0 skipped** (Phase 3 certified floor).
> If count differs, stop and report — do not proceed.

---

## §0 Context

Phase 3 delivered the Twin Protocol — certified at 149/0/0, 96% coverage.

Phase 3.5 delivers **five developer tools** that make DuggerBot the shared state
layer between Claude and Devin. Without these tools, Robert manually pastes Devin's
terminal output to Claude for verification. With them, Claude calls
`verify_test_floor()` directly and confirms Devin's work without Robert
transcribing anything. Robert's role becomes approval and decision — not transport.

These tools are also live when Phase 4 (RALPH) starts. Claude can verify RALPH's
own implementation using DuggerBot. The tether verifies itself during the hardest
phase.

**ADR-008 minor correction (no new ADR required):**
ADR-008 designated developer tools as "Devin only." The tether design requires
Claude to call `verify_test_floor()` and `check_coverage()` too. All five
developer tools are accessible to **both** `CallerIdentity.CLAUDE` and
`CallerIdentity.DEVIN`. Read-only, no budget impact, no routing risk.

**What Phase 3.5 produces:**
- `mcp/dev_tools.py` — five handlers + async subprocess helper
- `mcp/tools.py` modified — `get_dev_tool_list()` added
- `mcp/server.py` modified — dev tools registered on MCP server
- `mcp/handlers.py` modified — routes dev tool calls for both caller identities
- 23 new tests, 0 failures, 0 skipped
- 80%+ coverage on new file, overall floor maintained

**What Phase 3.5 does NOT produce:**
- New modules, new servers, new architecture
- Any tool that modifies state — all five are strictly read-only
- Telegram integration
- RALPH or any Phase 4 work

---

## §1 Scope

| File | Status | Action |
|---|---|---|
| `duggerbot/mcp/dev_tools.py` | New | Five handlers + `_run_command()` helper |
| `duggerbot/mcp/tools.py` | Modify | Add `get_dev_tool_list()` |
| `duggerbot/mcp/server.py` | Modify | Register dev tools alongside production tools |
| `duggerbot/mcp/handlers.py` | Modify | Route dev tool calls, both CallerIdentities |
| `tests/mcp/test_dev_tools.py` | New | 15 tests |
| `tests/mcp/test_tools.py` | Modify | 5 new tool schema tests |
| `tests/mcp/test_handlers.py` | Modify | 3 new routing tests |
| `docs/state/current.md` | Modify | Update as final step only |

**Read-only — do not touch:**
All `duggerbot/router/`, `duggerbot/twins/`, `duggerbot/soul/`, `duggerbot/ralph/`,
all `docs/adr/`, soul documents, `.gitignore`, config YAML files,
`tests/router/`, `tests/twins/`, `tests/soul/`

---

## §2 Implementation

---

### 2.1 `duggerbot/mcp/dev_tools.py` (NEW)

> ⚠️ **RULE:** `_run_command()` must use `asyncio.create_subprocess_exec` —
> never `subprocess.run`, never `asyncio.create_subprocess_shell`.
> Shell injection risk and event loop blocking are both unacceptable.

> ⚠️ **RULE:** All five handlers are read-only. No handler writes to disk,
> modifies state, or makes network calls. If a handler needs to write a
> temporary file (coverage JSON), it must delete it in a `finally` block.

> ⚠️ **RULE:** Subprocess timeouts must kill the process and clean up.
> A hung pytest must never hang the MCP server. `asyncio.TimeoutError` is
> caught, process is killed, error TextContent is returned.

```python
import asyncio
import json
import tempfile
from pathlib import Path

from mcp.types import TextContent  # reference PrivyBot for exact import


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

async def _run_command(
    args: list[str],
    timeout: float,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    """
    Run a subprocess with timeout.
    Returns (returncode, stdout, stderr).
    Raises asyncio.TimeoutError if timeout exceeded — caller handles it.
    Kills process and awaits cleanup before raising.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return proc.returncode, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_verify_test_floor(arguments: dict) -> list[TextContent]:
    """
    Run: uv run pytest --tb=no -q
    Parse the summary line: "X passed, Y failed, Z skipped in N.Ns"
    Return structured JSON:
    {
        "passed": int,
        "failed": int,
        "skipped": int,
        "floor_met": bool,   # True iff failed == 0 and skipped == 0
        "raw_summary": str,
        "error": str | null
    }
    """
    try:
        _, stdout, stderr = await _run_command(
            ["uv", "run", "pytest", "--tb=no", "-q"],
            timeout=120.0,
        )
        return [TextContent(type="text", text=_parse_pytest_summary(stdout))]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text=json.dumps({
            "error": "pytest timed out after 120 seconds",
            "passed": 0, "failed": 0, "skipped": 0,
            "floor_met": False, "raw_summary": "",
        }))]


def _parse_pytest_summary(output: str) -> str:
    """
    Parse pytest -q output for the summary line.
    Handles: "X passed", "X passed, Y failed", "X passed, Y failed, Z skipped"
    Returns JSON string.
    """
    # The summary line is the last non-empty line containing "passed"
    passed = failed = skipped = 0
    raw_summary = ""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            raw_summary = line
            # Parse counts using simple string scanning
            import re
            for match in re.finditer(r'(\d+)\s+(passed|failed|skipped|error)', line):
                count, label = int(match.group(1)), match.group(2)
                if label == "passed":
                    passed = count
                elif label in ("failed", "error"):
                    failed += count
                elif label == "skipped":
                    skipped = count
            break
    return json.dumps({
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "floor_met": failed == 0 and skipped == 0,
        "raw_summary": raw_summary,
        "error": None,
    })


async def handle_check_coverage(arguments: dict) -> list[TextContent]:
    """
    Run: uv run pytest --cov=duggerbot --cov-report=json:<tmpfile> --tb=no -q
    Read the JSON coverage report.
    Return structured JSON:
    {
        "overall_percent": float,
        "modules": { "module/path.py": float, ... },
        "floor_met": bool,   # True iff overall_percent >= 80.0
        "error": str | null
    }
    Always deletes the temp file.
    """
    report_path = Path(tempfile.mktemp(suffix=".json", prefix="duggerbot_cov_"))
    try:
        await _run_command(
            [
                "uv", "run", "pytest",
                "--cov=duggerbot",
                f"--cov-report=json:{report_path}",
                "--tb=no", "-q",
            ],
            timeout=180.0,
        )
        if not report_path.exists():
            return [TextContent(type="text", text=json.dumps({
                "error": "coverage report not generated",
                "overall_percent": 0.0,
                "modules": {},
                "floor_met": False,
            }))]
        data = json.loads(report_path.read_text())
        overall = data.get("totals", {}).get("percent_covered", 0.0)
        modules = {
            k: v.get("summary", {}).get("percent_covered", 0.0)
            for k, v in data.get("files", {}).items()
        }
        return [TextContent(type="text", text=json.dumps({
            "overall_percent": round(overall, 1),
            "modules": {k: round(v, 1) for k, v in modules.items()},
            "floor_met": overall >= 80.0,
            "error": None,
        }))]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text=json.dumps({
            "error": "coverage check timed out after 180 seconds",
            "overall_percent": 0.0,
            "modules": {},
            "floor_met": False,
        }))]
    finally:
        if report_path.exists():
            report_path.unlink()


async def handle_get_project_state(arguments: dict) -> list[TextContent]:
    """
    Read docs/state/current.md.
    Return structured JSON: {phase, certified_floor, what_is_next, raw, error}
    """
    state_path = Path("docs/state/current.md")
    if not state_path.exists():
        return [TextContent(type="text", text=json.dumps({
            "error": "docs/state/current.md not found",
        }))]
    raw = state_path.read_text()
    parsed = {}
    for line in raw.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            parsed[key.strip()] = value.strip().strip("'\"")
    return [TextContent(type="text", text=json.dumps({
        "phase": parsed.get("phase", "unknown"),
        "certified_floor": parsed.get("certified_floor", "unknown"),
        "what_is_next": parsed.get("what_is_next", "unknown"),
        "raw": raw,
        "error": None,
    }))]


async def handle_get_open_issues(arguments: dict) -> list[TextContent]:
    """
    Read all ISSUE-*.md files from docs/issues/.
    Return structured JSON: {issues: [{id, title, severity, status, summary}]}
    """
    issues_dir = Path("docs/issues")
    if not issues_dir.exists():
        return [TextContent(type="text", text=json.dumps({"issues": []}))]
    issues = []
    for issue_file in sorted(issues_dir.glob("ISSUE-*.md")):
        content = issue_file.read_text()
        issue = {"id": issue_file.stem, "title": "", "severity": "", "status": "open", "summary": ""}
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                issue["title"] = line.removeprefix("# ").strip()
            elif line.lower().startswith("**severity"):
                issue["severity"] = line.split(":", 1)[-1].strip().strip("*")
            elif line.lower().startswith("**status"):
                issue["status"] = line.split(":", 1)[-1].strip().strip("*")
            elif line.lower().startswith("**problem"):
                # Next non-empty line is the summary
                pass
        issues.append(issue)
    return [TextContent(type="text", text=json.dumps({"issues": issues, "count": len(issues)}))]


async def handle_get_migration_manifest(arguments: dict) -> list[TextContent]:
    """
    Read migration_manifest.json if it exists.
    Return the JSON content directly, or error if missing.
    """
    manifest_path = Path("migration_manifest.json")
    if not manifest_path.exists():
        return [TextContent(type="text", text=json.dumps({
            "error": "migration_manifest.json not found — run migrate_privybot.py first"
        }))]
    return [TextContent(type="text", text=manifest_path.read_text())]


# ---------------------------------------------------------------------------
# Dispatch table (mirrors TOOL_HANDLERS pattern from handlers.py)
# ---------------------------------------------------------------------------

DEV_TOOL_HANDLERS = {
    "verify_test_floor": handle_verify_test_floor,
    "check_coverage": handle_check_coverage,
    "get_project_state": handle_get_project_state,
    "get_open_issues": handle_get_open_issues,
    "get_migration_manifest": handle_get_migration_manifest,
}
```

---

### 2.2 `duggerbot/mcp/tools.py` modification

Add `get_dev_tool_list()` alongside the existing `get_tool_list()`.

> ⚠️ **RULE:** Do not modify `get_tool_list()`. Add `get_dev_tool_list()`
> as a separate function. The server registers both. The distinction is
> preserved for introspection — callers can see which tools are which.

The five dev tool schemas:

| Tool | Params | Description |
|---|---|---|
| `verify_test_floor` | none | Run pytest, return pass/fail/skip counts and floor_met bool |
| `check_coverage` | none | Run coverage, return per-module percentages and floor_met bool |
| `get_project_state` | none | Read docs/state/current.md, return structured phase state |
| `get_open_issues` | none | Read docs/issues/, return list of open issues with severity |
| `get_migration_manifest` | none | Read migration_manifest.json, return tool utilization data |

All five have empty `required` lists — no parameters required.

---

### 2.3 `duggerbot/mcp/handlers.py` modification

Add routing for dev tools. Both `CallerIdentity.CLAUDE` and `CallerIdentity.DEVIN`
can call any dev tool.

> ⚠️ **RULE:** The existing Devin routing restriction (no Claude API budget)
> still applies to production tools. Dev tools have no routing — they make
> no provider calls. No restriction needed.

In the `call_tool` handler:
```python
# Check dev tools first
if name in DEV_TOOL_HANDLERS:
    return await DEV_TOOL_HANDLERS[name](arguments)

# Then production tools (existing logic)
if name in TOOL_HANDLERS:
    ...
```

---

### 2.4 `duggerbot/mcp/server.py` modification

Register dev tools in the `list_tools` handler:

```python
@server.list_tools()
async def list_tools():
    return get_tool_list() + get_dev_tool_list()
```

> ⚠️ **RULE:** This is the only change to server.py in Phase 3.5.
> Do not touch the lifespan, SSE endpoint, or any other server code.

---

## §3 Test Anchors

No subprocess calls in tests. Mock `_run_command` with `pytest-mock`.
No real pytest execution inside tests. No real file I/O for manifest tests
(use `tmp_path`). `get_project_state` and `get_open_issues` tests use
`tmp_path` with real file content.

Target: **23 new tests**
Full suite target: **172+ passed, 0 failed, 0 skipped**

---

### `tests/mcp/test_dev_tools.py` — 15 tests

| Test | Behaviour |
|---|---|
| `test_verify_floor_returns_structured_json` | Returns dict with passed/failed/skipped/floor_met |
| `test_verify_floor_parses_passed_count` | "35 passed" → passed=35 |
| `test_verify_floor_parses_failed_count` | "2 failed" → failed=2, floor_met=False |
| `test_verify_floor_floor_met_true_when_clean` | 0 failed, 0 skipped → floor_met=True |
| `test_verify_floor_floor_met_false_when_skipped` | Any skipped → floor_met=False |
| `test_verify_floor_returns_error_on_timeout` | TimeoutError → error field, floor_met=False |
| `test_check_coverage_returns_overall_percent` | Mocked JSON report → overall_percent float |
| `test_check_coverage_returns_module_dict` | modules dict with file paths as keys |
| `test_check_coverage_floor_met_above_80` | overall=97.0 → floor_met=True |
| `test_check_coverage_floor_met_below_80` | overall=75.0 → floor_met=False |
| `test_check_coverage_returns_error_on_timeout` | TimeoutError → error field |
| `test_get_project_state_returns_phase` | Reads current.md → phase field populated |
| `test_get_project_state_error_when_missing` | No current.md → error field |
| `test_get_open_issues_returns_list` | Two issue files → issues list length 2 |
| `test_get_open_issues_empty_when_no_dir` | No docs/issues/ → issues=[] |
| `test_get_migration_manifest_returns_json` | manifest.json exists → content returned |
| `test_get_migration_manifest_error_when_missing` | No manifest → error field |

(17 tests — update target to 25 new tests total.)

---

### `tests/mcp/test_tools.py` additions — 5 tests

| Test | Behaviour |
|---|---|
| `test_dev_tool_list_has_five_tools` | `get_dev_tool_list()` returns list of length 5 |
| `test_verify_test_floor_schema_valid` | Has name, description, empty required |
| `test_check_coverage_schema_valid` | Has name, description, empty required |
| `test_get_project_state_schema_valid` | Has name, description, empty required |
| `test_get_open_issues_schema_valid` | Has name, description, empty required |

---

### `tests/mcp/test_handlers.py` additions — 3 tests

| Test | Behaviour |
|---|---|
| `test_claude_caller_can_call_verify_test_floor` | CLAUDE identity → routes to dev tool |
| `test_devin_caller_can_call_verify_test_floor` | DEVIN identity → routes to dev tool |
| `test_dev_tool_keys_match_dev_tool_list` | DEV_TOOL_HANDLERS keys == dev tool names |

---

## §4 Completion Criteria

- [ ] `uv run pytest tests/mcp/test_dev_tools.py` reports **17 passed, 0 failed, 0 skipped**
- [ ] Full suite: **≥172 passed, 0 failed, 0 skipped**
- [ ] `--cov=duggerbot/mcp/dev_tools --cov-fail-under=80` passes
- [ ] `dev_tools.py` ≥ 80% coverage (paste from `--cov-report=term-missing`)
- [ ] `_run_command()` uses `asyncio.create_subprocess_exec` — confirm by reading file
- [ ] `_run_command()` kills process on TimeoutError and awaits cleanup — confirm by reading file
- [ ] Coverage JSON report written to temp path and deleted in `finally` — confirm by reading file
- [ ] Both `CallerIdentity.CLAUDE` and `CallerIdentity.DEVIN` route to dev tools (test-enforced)
- [ ] `list_tools()` in server returns all 10 tools (5 production + 5 dev) — manual: call the endpoint
- [ ] `DEV_TOOL_HANDLERS` keys match `get_dev_tool_list()` names (test-enforced)
- [ ] ISSUE-001 still open — confirm no regression on router.py
- [ ] `docs/state/current.md` updated

**Proof required:**
```
Full pytest output: exact line showing "X passed, 0 failed, 0 skipped"
Coverage output: dev_tools.py line from --cov-report=term-missing
```

---

## §5 Quick Reference

| Fact | Value |
|---|---|
| Phase | 3.5 — Developer Tools Tether |
| Pre-flight | 149/0/0 (Phase 3 certified) |
| New tests | 25 (17 dev_tools + 5 tools + 3 handlers) |
| Full suite target | ≥172/0/0 |
| New file | `mcp/dev_tools.py` only |
| Subprocess tool | `asyncio.create_subprocess_exec` — mandatory |
| Subprocess timeout | `verify_test_floor`: 120s, `check_coverage`: 180s |
| Coverage temp file | Written to `tempfile.mktemp()`, deleted in `finally` |
| Caller access | Both CLAUDE and DEVIN can call all 5 dev tools |
| Dev tools | verify_test_floor, check_coverage, get_project_state, get_open_issues, get_migration_manifest |
| Production tools | Unchanged — 5 tools, Devin routing restriction unchanged |
| Read-only | router/, twins/, ralph/, soul/, all ADRs, soul docs, config YAMLs, .gitignore |
| Next phase | Phase 4 — RALPH Rebuilt |
