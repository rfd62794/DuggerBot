"""Developer tools — read-only tether for Claude and Devin verification."""

import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from mcp.types import TextContent

from duggerbot.context_store import delete_context, list_context, read_context, write_context
from duggerbot.directives import (
    write_active_directive,
    get_active_directive,
    get_current_step,
    advance_step,
    escalate_step,
    Directive,
)


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
# Completion memory helper
# ---------------------------------------------------------------------------

async def _write_completion_memory_to_store(directive: dict) -> None:
    """Write directive completion summary to context store under memory: namespace.

    Key: memory:directive:{id}:complete
    Value: JSON summary — id, title, steps completed, completed_at
    """
    import datetime
    directive_id = directive.get("id", "unknown")
    steps = directive.get("steps", [])
    completed_count = sum(1 for s in steps if s.get("status") == "complete")

    summary = {
        "directive_id": directive_id,
        "title": directive.get("title", ""),
        "description": directive.get("description", ""),
        "steps_completed": completed_count,
        "total_steps": len(steps),
        "status": "complete",
        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

    key = f"memory:directive:{directive_id}:complete"
    await write_context(key, json.dumps(summary))


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

async def handle_verify_test_floor(arguments: dict) -> list[TextContent]:
    """Run pytest --tb=line -q. Return structured pass/fail/skip counts with stderr."""
    try:
        _, stdout, stderr = await _run_command(
            [sys.executable, "-m", "pytest", "--tb=line", "-q"],
            timeout=120.0,
        )
        # Include stderr (failure details) in raw_summary
        combined = stdout + "\n" + stderr if stderr else stdout
        return [TextContent(type="text", text=_parse_pytest_summary(combined))]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text=json.dumps({
            "error": "pytest timed out after 120 seconds",
            "passed": 0, "failed": 0, "skipped": 0,
            "floor_met": False, "raw_summary": "",
        }))]


async def handle_verify_floor(arguments: dict) -> list[TextContent]:
    """Run pytest in an arbitrary repo root. Return structured pass/fail/skip counts."""
    repo_path = arguments.get("repo_path", "")
    if not repo_path or not Path(repo_path).is_dir():
        return [TextContent(type="text", text=json.dumps({
            "repo_path": repo_path,
            "error": f"Invalid or missing repo_path: {repo_path!r}",
            "passed": 0, "failed": 0, "skipped": 0,
            "floor_met": False, "raw_summary": "",
        }))]
    try:
        _, stdout, stderr = await _run_command(
            [sys.executable, "-m", "pytest", "--tb=line", "-q"],
            timeout=120.0,
            cwd=repo_path,
        )
        combined = stdout + "\n" + stderr if stderr else stdout
        result = json.loads(_parse_pytest_summary(combined))
        result["repo_path"] = repo_path
        return [TextContent(type="text", text=json.dumps(result))]
    except asyncio.TimeoutError:
        return [TextContent(type="text", text=json.dumps({
            "repo_path": repo_path,
            "error": "pytest timed out after 120 seconds",
            "passed": 0, "failed": 0, "skipped": 0,
            "floor_met": False, "raw_summary": "",
        }))]


def _parse_pytest_summary(output: str) -> str:
    """
    Parse pytest -q output for the summary line.
    Handles: "X passed", "X passed, Y failed", "X passed, Y failed, Z skipped"
    Returns JSON string with full output in raw_summary.
    """
    passed = failed = skipped = 0
    summary_line = ""
    # Find summary line from the end
    for line in reversed(output.splitlines()):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            summary_line = line
            for match in re.finditer(r'(\d+)\s+(passed|failed|skipped|error)', line):
                count, label = int(match.group(1)), match.group(2)
                if label == "passed":
                    passed = count
                elif label in ("failed", "error"):
                    failed += count
                elif label == "skipped":
                    skipped = count
            break
    # Include full output (truncated if too long)
    raw_summary = output[:2000] if len(output) > 2000 else output
    return json.dumps({
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "floor_met": failed == 0 and skipped == 0,
        "raw_summary": raw_summary,
        "error": None,
    })


async def handle_check_coverage(arguments: dict) -> list[TextContent]:
    """Run coverage, return per-module percentages and floor_met bool."""
    report_path = Path(tempfile.mktemp(suffix=".json", prefix="duggerbot_cov_"))
    try:
        await _run_command(
            [
                sys.executable, "-m", "pytest",
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
    """Read docs/state/current.md. Return structured phase state."""
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
    """Read all ISSUE-*.md files from docs/issues/. Return structured list."""
    issues_dir = Path("docs/issues")
    if not issues_dir.exists():
        return [TextContent(type="text", text=json.dumps({"issues": [], "count": 0}))]
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
        issues.append(issue)
    return [TextContent(type="text", text=json.dumps({"issues": issues, "count": len(issues)}))]


async def handle_get_migration_manifest(arguments: dict) -> list[TextContent]:
    """Read migration_manifest.json if it exists."""
    manifest_path = Path("migration_manifest.json")
    if not manifest_path.exists():
        return [TextContent(type="text", text=json.dumps({
            "error": "migration_manifest.json not found — run migrate_privybot.py first"
        }))]
    return [TextContent(type="text", text=manifest_path.read_text())]


async def handle_get_version(arguments: dict) -> list[TextContent]:
    """Return current version string, revision, git hash, and instance role. Fast — no network."""
    import os as _os
    from duggerbot.version import get_version_string, get_revision, get_git_hash
    return [TextContent(type="text", text=json.dumps({
        "version": get_version_string(),
        "revision": get_revision(),
        "git_hash": get_git_hash(),
        "instance_role": _os.environ.get("INSTANCE_ROLE", "unknown"),
        "error": None,
    }))]


async def handle_check_for_update(arguments: dict) -> list[TextContent]:
    """Check if a newer version is available on origin/main. Slow — performs git fetch."""
    from duggerbot.version import get_revision, get_remote_revision
    loop = asyncio.get_event_loop()
    local = await loop.run_in_executor(None, get_revision)
    remote = await loop.run_in_executor(None, get_remote_revision)
    return [TextContent(type="text", text=json.dumps({
        "local_revision": local,
        "remote_revision": remote,
        "update_available": remote > local and remote > 0,
        "error": None,
    }))]


async def handle_write_context(arguments: dict) -> list[TextContent]:
    """Write or overwrite a context entry."""
    key = arguments.get("key", "")
    value = arguments.get("value", "")
    if not key:
        return [TextContent(type="text", text=json.dumps({"error": "key is required"}))]
    await write_context(key, value)
    return [TextContent(type="text", text=json.dumps({
        "key": key, "written": True, "error": None,
    }))]


async def handle_read_context(arguments: dict) -> list[TextContent]:
    """Read a context entry by key."""
    key = arguments.get("key", "")
    if not key:
        return [TextContent(type="text", text=json.dumps({"error": "key is required"}))]
    value = await read_context(key)
    return [TextContent(type="text", text=json.dumps({
        "key": key, "value": value, "found": value is not None, "error": None,
    }))]


async def handle_delete_context(arguments: dict) -> list[TextContent]:
    """Delete a context entry by key."""
    key = arguments.get("key", "")
    if not key:
        return [TextContent(type="text", text=json.dumps({"error": "key is required"}))]
    deleted = await delete_context(key)
    return [TextContent(type="text", text=json.dumps({
        "key": key, "deleted": deleted, "error": None,
    }))]


async def handle_list_context(arguments: dict) -> list[TextContent]:
    """List context keys, optionally filtered by prefix."""
    prefix = arguments.get("prefix", "")
    keys = await list_context(prefix)
    return [TextContent(type="text", text=json.dumps({
        "keys": keys, "count": len(keys), "error": None,
    }))]


async def handle_dispatch_to_cline(arguments: dict) -> list[TextContent]:
    """Dispatch a task to Cline CLI headless. Provider and model from env vars."""
    task = arguments.get("task", "")
    model = arguments.get("model", "")
    if not task or not model:
        return [TextContent(type="text", text=json.dumps({"error": "task and model are required"}))]

    timeout = int(os.environ.get("CLINE_TIMEOUT_SECONDS", "300"))
    repo_root = str(Path(__file__).parent.parent.parent)
    cline_cmd = os.environ.get("CLINE_PATH", "cline")
    provider = os.environ.get("CLINE_PROVIDER", "anthropic")  # no longer defaults to ollama

    proc = await asyncio.create_subprocess_exec(
        cline_cmd, task,
        "--provider", provider,
        "--model", model,
        "--auto-approve", "true",
        "--cwd", repo_root,
        "--timeout", str(timeout),
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout + 10
        )
        output = stdout.decode().strip() or stderr.decode().strip()
        return [TextContent(type="text", text=json.dumps({
            "success": proc.returncode == 0,
            "output": output,
            "model": model,
            "provider": provider,
            "error": None,
        }))]
    except asyncio.TimeoutError:
        proc.kill()
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "output": "Timed out",
            "model": model,
            "provider": provider,
            "error": "timeout",
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "output": str(e),
            "model": model,
            "provider": provider,
            "error": str(e),
        }))]


async def handle_read_file(arguments: dict) -> list[TextContent]:
    """Read a file by absolute or repo-relative path. Returns content as text."""
    file_path = arguments.get("path", "")
    if not file_path:
        return [TextContent(type="text", text=json.dumps({"error": "path is required"}))]
    p = Path(file_path)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        return [TextContent(type="text", text=json.dumps({"error": f"File not found: {p}"}))]
    if not p.is_file():
        return [TextContent(type="text", text=json.dumps({"error": f"Not a file: {p}"}))]
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    return [TextContent(type="text", text=json.dumps({
        "path": str(p),
        "content": content,
        "lines": len(content.splitlines()),
        "error": None,
    }))]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

async def handle_get_logs(arguments: dict) -> list[TextContent]:
    """Return last N lines of logs/duggerbot.log."""
    lines = int(arguments.get("lines", 50))
    log_path = Path("logs/duggerbot.log")

    if not log_path.exists():
        return [TextContent(type="text", text=json.dumps(
            {"error": "logs/duggerbot.log not found", "lines": []}
        ))]

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        tail = all_lines[-lines:] if len(all_lines) >= lines else all_lines
        return [TextContent(type="text", text=json.dumps(
            {"lines": tail, "count": len(tail), "total_lines": len(all_lines)}
        ))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "lines": []}))]


# ---------------------------------------------------------------------------
# Directive management handlers (Phase 4a.2)
# ---------------------------------------------------------------------------

async def handle_write_directive(arguments: dict) -> list[TextContent]:
    """Store a full directive, set step 1 as current."""
    import json
    directive_json = arguments.get("directive", "")
    if not directive_json:
        return [TextContent(type="text", text=json.dumps({"error": "directive JSON is required"}))]
    
    try:
        directive: Directive = json.loads(directive_json)
        await write_active_directive(directive)
        step_count = len(directive.get("steps", []))
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "directive_id": directive.get("id"),
            "step_count": step_count,
            "current_step": 1,
            "error": None,
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_get_current_step(arguments: dict) -> list[TextContent]:
    """Get the current step for the active directive."""
    step_num, step = await get_current_step()
    if step is None:
        return [TextContent(type="text", text=json.dumps({
            "has_active_directive": False,
            "step_number": 0,
            "step": None,
            "error": None,
        }))]
    
    return [TextContent(type="text", text=json.dumps({
        "has_active_directive": True,
        "step_number": step_num,
        "step": step,
        "error": None,
    }))]


async def handle_complete_step(arguments: dict) -> list[TextContent]:
    """Mark step complete and advance to next."""
    step_id = arguments.get("step_id", 0)
    if not step_id:
        return [TextContent(type="text", text=json.dumps({"error": "step_id is required"}))]

    try:
        has_more = await advance_step(int(step_id))

        if not has_more:
            # Directive complete — write to memory namespace in context store
            directive = await get_active_directive()
            if directive:
                await _write_completion_memory_to_store(directive)

        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "has_more_steps": has_more,
            "next_step": int(step_id) + 1 if has_more else None,
            "error": None,
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_escalate_step(arguments: dict) -> list[TextContent]:
    """Escalate a step (halt directive, notify Claude)."""
    step_id = arguments.get("step_id", 0)
    reason = arguments.get("reason", "")
    
    if not step_id or not reason:
        return [TextContent(type="text", text=json.dumps({"error": "step_id and reason are required"}))]
    
    try:
        await escalate_step(int(step_id), reason)
        return [TextContent(type="text", text=json.dumps({
            "success": True,
            "step_id": step_id,
            "reason": reason,
            "status": "escalated",
            "error": None,
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]


async def handle_get_directive_status(arguments: dict) -> list[TextContent]:
    """Get full status of active directive."""
    directive = await get_active_directive()
    step_num, current_step = await get_current_step()
    
    if directive is None:
        return [TextContent(type="text", text=json.dumps({
            "has_active_directive": False,
            "error": None,
        }))]
    
    steps = directive.get("steps", [])
    completed = sum(1 for s in steps if s.get("status") == "complete")
    
    return [TextContent(type="text", text=json.dumps({
        "has_active_directive": True,
        "directive_id": directive.get("id"),
        "title": directive.get("title"),
        "total_steps": len(steps),
        "completed_steps": completed,
        "current_step": step_num,
        "current_step_status": current_step.get("status") if current_step else None,
        "error": None,
    }))]


DEV_TOOL_HANDLERS = {
    "verify_test_floor": handle_verify_test_floor,
    "check_coverage": handle_check_coverage,
    "get_project_state": handle_get_project_state,
    "get_open_issues": handle_get_open_issues,
    "get_migration_manifest": handle_get_migration_manifest,
    "get_version": handle_get_version,
    "check_for_update": handle_check_for_update,
    "read_file": handle_read_file,
    "write_context": handle_write_context,
    "read_context": handle_read_context,
    "delete_context": handle_delete_context,
    "list_context": handle_list_context,
    "dispatch_to_cline": handle_dispatch_to_cline,
    "get_logs": handle_get_logs,
    "write_directive": handle_write_directive,
    "get_current_step": handle_get_current_step,
    "complete_step": handle_complete_step,
    "escalate_step": handle_escalate_step,
    "get_directive_status": handle_get_directive_status,
    "verify_floor": handle_verify_floor,
}
