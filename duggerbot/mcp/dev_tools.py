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
    """Run pytest --tb=no -q. Return structured pass/fail/skip counts."""
    try:
        _, stdout, stderr = await _run_command(
            [sys.executable, "-m", "pytest", "--tb=no", "-q"],
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
    passed = failed = skipped = 0
    raw_summary = ""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if "passed" in line or "failed" in line or "error" in line:
            raw_summary = line
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
    """Dispatch a task to Cline CLI headless with Ollama provider."""
    task = arguments.get("task", "")
    model = arguments.get("model", "")
    if not task or not model:
        return [TextContent(type="text", text=json.dumps({"error": "task and model are required"}))]

    timeout = int(os.environ.get("CLINE_TIMEOUT_SECONDS", "300"))
    repo_root = str(Path(__file__).parent.parent.parent)

    proc = await asyncio.create_subprocess_exec(
        "cline", task,
        "--provider", "ollama",
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
            "error": None,
        }))]
    except asyncio.TimeoutError:
        proc.kill()
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "output": "Timed out",
            "model": model,
            "error": "timeout",
        }))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "output": str(e),
            "model": model,
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
}
