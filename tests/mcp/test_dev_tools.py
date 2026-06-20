"""Tests for duggerbot.mcp.dev_tools — Phase 3.5."""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from duggerbot.mcp.dev_tools import (
    DEV_TOOL_HANDLERS,
    _parse_pytest_summary,
    _run_command,
    handle_check_coverage,
    handle_check_for_update,
    handle_complete_step,
    handle_delete_context,
    handle_dispatch_to_cline,
    handle_get_logs,
    handle_get_migration_manifest,
    handle_get_open_issues,
    handle_get_project_state,
    handle_get_version,
    handle_list_context,
    handle_read_context,
    handle_verify_floor,
    handle_verify_test_floor,
    handle_write_context,
)


# ---------------------------------------------------------------------------
# _parse_pytest_summary
# ---------------------------------------------------------------------------

def test_verify_floor_returns_structured_json():
    """Returns dict with passed/failed/skipped/floor_met."""
    raw = _parse_pytest_summary("149 passed in 1.53s")
    data = json.loads(raw)
    assert "passed" in data
    assert "failed" in data
    assert "skipped" in data
    assert "floor_met" in data


def test_verify_floor_parses_passed_count():
    """"35 passed" → passed=35."""
    data = json.loads(_parse_pytest_summary("35 passed in 0.8s"))
    assert data["passed"] == 35


def test_verify_floor_parses_failed_count():
    """"2 failed" → failed=2, floor_met=False."""
    data = json.loads(_parse_pytest_summary("33 passed, 2 failed in 0.8s"))
    assert data["failed"] == 2
    assert data["floor_met"] is False


def test_verify_floor_floor_met_true_when_clean():
    """0 failed, 0 skipped → floor_met=True."""
    data = json.loads(_parse_pytest_summary("149 passed in 1.5s"))
    assert data["floor_met"] is True
    assert data["failed"] == 0
    assert data["skipped"] == 0


def test_verify_floor_floor_met_false_when_skipped():
    """Any skipped → floor_met=False."""
    data = json.loads(_parse_pytest_summary("147 passed, 2 skipped in 1.5s"))
    assert data["floor_met"] is False
    assert data["skipped"] == 2


# ---------------------------------------------------------------------------
# handle_verify_test_floor
# ---------------------------------------------------------------------------

async def test_verify_floor_returns_error_on_timeout():
    """TimeoutError → error field, floor_met=False."""
    with patch("duggerbot.mcp.dev_tools._run_command", side_effect=asyncio.TimeoutError):
        result = await handle_verify_test_floor({})
        data = json.loads(result[0].text)
        assert data["error"] is not None
        assert data["floor_met"] is False


# ---------------------------------------------------------------------------
# handle_check_coverage
# ---------------------------------------------------------------------------

async def test_check_coverage_returns_overall_percent(tmp_path, monkeypatch):
    """Mocked JSON report → overall_percent float."""
    report = {
        "totals": {"percent_covered": 97.3},
        "files": {
            "duggerbot/mcp/auth.py": {"summary": {"percent_covered": 100.0}},
        },
    }

    async def fake_run_command(*args, **kwargs):
        # Write the report file to the path extracted from args
        for arg in args[0]:
            if arg.startswith("--cov-report=json:"):
                path = arg.split(":", 1)[1]
                from pathlib import Path
                Path(path).write_text(json.dumps(report))
        return 0, "", ""

    with patch("duggerbot.mcp.dev_tools._run_command", side_effect=fake_run_command):
        result = await handle_check_coverage({})
        data = json.loads(result[0].text)
        assert data["overall_percent"] == 97.3
        assert data["error"] is None


async def test_check_coverage_returns_module_dict(tmp_path, monkeypatch):
    """modules dict with file paths as keys."""
    report = {
        "totals": {"percent_covered": 95.0},
        "files": {
            "duggerbot/mcp/auth.py": {"summary": {"percent_covered": 100.0}},
            "duggerbot/twins/state.py": {"summary": {"percent_covered": 94.0}},
        },
    }

    async def fake_run_command(*args, **kwargs):
        for arg in args[0]:
            if arg.startswith("--cov-report=json:"):
                path = arg.split(":", 1)[1]
                from pathlib import Path
                Path(path).write_text(json.dumps(report))
        return 0, "", ""

    with patch("duggerbot.mcp.dev_tools._run_command", side_effect=fake_run_command):
        result = await handle_check_coverage({})
        data = json.loads(result[0].text)
        assert "duggerbot/mcp/auth.py" in data["modules"]
        assert "duggerbot/twins/state.py" in data["modules"]


async def test_check_coverage_floor_met_above_80(tmp_path):
    """overall=97.0 → floor_met=True."""
    report = {"totals": {"percent_covered": 97.0}, "files": {}}

    async def fake_run_command(*args, **kwargs):
        for arg in args[0]:
            if arg.startswith("--cov-report=json:"):
                from pathlib import Path
                Path(arg.split(":", 1)[1]).write_text(json.dumps(report))
        return 0, "", ""

    with patch("duggerbot.mcp.dev_tools._run_command", side_effect=fake_run_command):
        result = await handle_check_coverage({})
        data = json.loads(result[0].text)
        assert data["floor_met"] is True


async def test_check_coverage_floor_met_below_80(tmp_path):
    """overall=75.0 → floor_met=False."""
    report = {"totals": {"percent_covered": 75.0}, "files": {}}

    async def fake_run_command(*args, **kwargs):
        for arg in args[0]:
            if arg.startswith("--cov-report=json:"):
                from pathlib import Path
                Path(arg.split(":", 1)[1]).write_text(json.dumps(report))
        return 0, "", ""

    with patch("duggerbot.mcp.dev_tools._run_command", side_effect=fake_run_command):
        result = await handle_check_coverage({})
        data = json.loads(result[0].text)
        assert data["floor_met"] is False


async def test_check_coverage_returns_error_on_timeout():
    """TimeoutError → error field."""
    with patch("duggerbot.mcp.dev_tools._run_command", side_effect=asyncio.TimeoutError):
        result = await handle_check_coverage({})
        data = json.loads(result[0].text)
        assert data["error"] is not None
        assert data["floor_met"] is False


# ---------------------------------------------------------------------------
# handle_get_project_state
# ---------------------------------------------------------------------------

async def test_get_project_state_returns_phase(tmp_path, monkeypatch):
    """Reads current.md → phase field populated."""
    state_file = tmp_path / "docs" / "state" / "current.md"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("phase: 'Phase 3 — Twin Protocol'\ncertified_floor: '149/0/0'\nwhat_is_next: 'Phase 4'\n")
    monkeypatch.chdir(tmp_path)
    result = await handle_get_project_state({})
    data = json.loads(result[0].text)
    assert data["phase"] == "Phase 3 — Twin Protocol"
    assert data["error"] is None


async def test_get_project_state_error_when_missing(tmp_path, monkeypatch):
    """No current.md → error field."""
    monkeypatch.chdir(tmp_path)
    result = await handle_get_project_state({})
    data = json.loads(result[0].text)
    assert data["error"] is not None


# ---------------------------------------------------------------------------
# handle_get_open_issues
# ---------------------------------------------------------------------------

async def test_get_open_issues_returns_list(tmp_path, monkeypatch):
    """Two issue files → issues list length 2."""
    issues_dir = tmp_path / "docs" / "issues"
    issues_dir.mkdir(parents=True)
    (issues_dir / "ISSUE-001-test.md").write_text("# Test Issue 1\n**Severity:** Low\n")
    (issues_dir / "ISSUE-002-test.md").write_text("# Test Issue 2\n**Severity:** High\n")
    monkeypatch.chdir(tmp_path)
    result = await handle_get_open_issues({})
    data = json.loads(result[0].text)
    assert data["count"] == 2
    assert len(data["issues"]) == 2


async def test_get_open_issues_empty_when_no_dir(tmp_path, monkeypatch):
    """No docs/issues/ → issues=[]."""
    monkeypatch.chdir(tmp_path)
    result = await handle_get_open_issues({})
    data = json.loads(result[0].text)
    assert data["issues"] == []
    assert data["count"] == 0


# ---------------------------------------------------------------------------
# handle_get_migration_manifest
# ---------------------------------------------------------------------------

async def test_get_migration_manifest_returns_json(tmp_path, monkeypatch):
    """manifest.json exists → content returned."""
    manifest = tmp_path / "migration_manifest.json"
    manifest.write_text(json.dumps({"tools": {"research": 42}}))
    monkeypatch.chdir(tmp_path)
    result = await handle_get_migration_manifest({})
    data = json.loads(result[0].text)
    assert data["tools"]["research"] == 42


async def test_get_migration_manifest_error_when_missing(tmp_path, monkeypatch):
    """No manifest → error field."""
    monkeypatch.chdir(tmp_path)
    result = await handle_get_migration_manifest({})
    data = json.loads(result[0].text)
    assert "error" in data


# ---------------------------------------------------------------------------
# handle_get_version
# ---------------------------------------------------------------------------

async def test_get_version_returns_version_string(monkeypatch):
    """Response JSON has 'version' key matching format."""
    monkeypatch.setenv("INSTANCE_ROLE", "development")
    with patch("duggerbot.version.subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        result_obj = MagicMock()
        result_obj.returncode = 0
        result_obj.stdout = "42\n"
        mock_run.return_value = result_obj
        result = await handle_get_version({})
        data = json.loads(result[0].text)
        assert "version" in data
        assert data["version"].startswith("0.1.0.r")
        assert data["error"] is None


async def test_get_version_returns_instance_role(monkeypatch):
    """Response JSON has 'instance_role' from env."""
    monkeypatch.setenv("INSTANCE_ROLE", "production")
    with patch("duggerbot.version.subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        result_obj = MagicMock()
        result_obj.returncode = 0
        result_obj.stdout = "1\n"
        mock_run.return_value = result_obj
        result = await handle_get_version({})
        data = json.loads(result[0].text)
        assert data["instance_role"] == "production"


# ---------------------------------------------------------------------------
# handle_check_for_update
# ---------------------------------------------------------------------------

async def test_check_for_update_returns_local_and_remote():
    """Response has local_revision, remote_revision."""
    with patch("duggerbot.version.subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        result_obj = MagicMock()
        result_obj.returncode = 0
        result_obj.stdout = "174\n"
        mock_run.return_value = result_obj
        result = await handle_check_for_update({})
        data = json.loads(result[0].text)
        assert "local_revision" in data
        assert "remote_revision" in data
        assert data["error"] is None


async def test_check_for_update_update_available_true():
    """remote > local → update_available True."""
    call_count = [0]
    def fake_run(*args, **kwargs):
        from unittest.mock import MagicMock
        call_count[0] += 1
        cmd = args[0]
        r = MagicMock()
        if "origin/main" in cmd:
            r.returncode = 0
            r.stdout = "200\n"
        elif "HEAD" in cmd:
            r.returncode = 0
            r.stdout = "174\n"
        else:
            r.returncode = 0
            r.stdout = ""
        return r

    with patch("duggerbot.version.subprocess.run", side_effect=fake_run):
        result = await handle_check_for_update({})
        data = json.loads(result[0].text)
        assert data["update_available"] is True


# ---------------------------------------------------------------------------
# Phase 3.8 — Context store + Cline dispatch handlers
# ---------------------------------------------------------------------------


async def test_handle_write_context_returns_written_true():
    """write_context mocked → handler returns {"written": True}."""
    with patch("duggerbot.mcp.dev_tools.write_context", new_callable=AsyncMock):
        result = await handle_write_context({"key": "test_key", "value": "test_val"})
        data = json.loads(result[0].text)
        assert data["written"] is True
        assert data["key"] == "test_key"


async def test_handle_read_context_returns_value_when_found():
    """read_context returns 'val' → handler returns {"found": True, "value": "val"}."""
    with patch("duggerbot.mcp.dev_tools.read_context", new_callable=AsyncMock, return_value="val"):
        result = await handle_read_context({"key": "k"})
        data = json.loads(result[0].text)
        assert data["found"] is True
        assert data["value"] == "val"


async def test_handle_read_context_returns_not_found():
    """read_context returns None → handler returns {"found": False, "value": None}."""
    with patch("duggerbot.mcp.dev_tools.read_context", new_callable=AsyncMock, return_value=None):
        result = await handle_read_context({"key": "missing"})
        data = json.loads(result[0].text)
        assert data["found"] is False
        assert data["value"] is None


async def test_handle_delete_context_returns_deleted_true():
    """delete_context returns True → handler returns {"deleted": True}."""
    with patch("duggerbot.mcp.dev_tools.delete_context", new_callable=AsyncMock, return_value=True):
        result = await handle_delete_context({"key": "doomed"})
        data = json.loads(result[0].text)
        assert data["deleted"] is True


async def test_handle_dispatch_to_cline_returns_output(monkeypatch):
    """Handler calls cline with correct args and returns subprocess output."""
    monkeypatch.setenv("CLINE_PROVIDER", "ollama")
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b'{"result": "done"}', b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await handle_dispatch_to_cline({"task": "fix the bug", "model": "ollama/qwen3"})
        data = json.loads(result[0].text)

        # Verify cline was called with correct arguments
        args = mock_exec.call_args[0]
        assert "cline" in args[0]
        assert "--provider" in args
        assert "ollama" in args
        assert "--model" in args
        assert "ollama/qwen3" in args
        assert "--auto-approve" in args
        assert "--json" in args

        assert data["success"] is True
        assert data["model"] == "ollama/qwen3"
        assert data["provider"] == "ollama"


async def test_get_logs_returns_tail_lines(tmp_path):
    """Mock log file with 100 lines, request 10 → returns last 10."""
    log_file = tmp_path / "duggerbot.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_lines = [f"Line {i}" for i in range(100)]
    log_file.write_text("\n".join(log_lines), encoding="utf-8")

    with patch("duggerbot.mcp.dev_tools.Path") as mock_path_class:
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = True
        mock_path_instance.read_text.return_value = "\n".join(log_lines)
        mock_path_class.return_value = mock_path_instance

        result = await handle_get_logs({"lines": 10})
        data = json.loads(result[0].text)
        assert "lines" in data
        assert data["count"] == 10
        assert data["total_lines"] == 100


async def test_get_logs_returns_error_when_file_missing():
    """No log file → error key in response."""
    with patch("duggerbot.mcp.dev_tools.Path") as mock_path_class:
        mock_path_instance = MagicMock()
        mock_path_instance.exists.return_value = False
        mock_path_class.return_value = mock_path_instance

        result = await handle_get_logs({"lines": 50})
        data = json.loads(result[0].text)
        assert "error" in data
        assert data["lines"] == []


# ---------------------------------------------------------------------------
# handle_verify_floor — cross-repo pytest runner
# ---------------------------------------------------------------------------

async def test_verify_floor_returns_passed_count_for_valid_repo(tmp_path):
    """Valid repo_path runs pytest and returns structured result with repo_path."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"5 passed in 0.5s", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        result = await handle_verify_floor({"repo_path": str(tmp_path)})
        data = json.loads(result[0].text)

    assert data["passed"] == 5
    assert data["failed"] == 0
    assert data["floor_met"] is True
    assert data["repo_path"] == str(tmp_path)


async def test_verify_floor_returns_error_for_invalid_path():
    """Missing or invalid repo_path returns error without running pytest."""
    result = await handle_verify_floor({"repo_path": "/nonexistent/path/xyz"})
    data = json.loads(result[0].text)

    assert data["floor_met"] is False
    assert "error" in data
    assert data["passed"] == 0


# ---------------------------------------------------------------------------
# handle_dispatch_to_cline — CLINE_PROVIDER env var tests
# ---------------------------------------------------------------------------

async def test_dispatch_uses_env_provider(monkeypatch):
    """CLINE_PROVIDER=anthropic → subprocess called with --provider anthropic."""
    monkeypatch.setenv("CLINE_PROVIDER", "anthropic")
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"done", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await handle_dispatch_to_cline({"task": "fix bug", "model": "claude-3"})
        data = json.loads(result[0].text)

    assert data["success"] is True
    assert data["provider"] == "anthropic"
    args = mock_exec.call_args[0]
    assert "--provider" in args
    assert "anthropic" in args


async def test_dispatch_defaults_to_anthropic(monkeypatch):
    """CLINE_PROVIDER not set → subprocess called with --provider anthropic (default)."""
    monkeypatch.delenv("CLINE_PROVIDER", raising=False)
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"done", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        result = await handle_dispatch_to_cline({"task": "fix bug", "model": "claude-3"})
        data = json.loads(result[0].text)

    assert data["success"] is True
    assert data["provider"] == "anthropic"
    args = mock_exec.call_args[0]
    assert "--provider" in args
    assert "anthropic" in args


async def test_dispatch_not_ollama(monkeypatch):
    """CLINE_PROVIDER not set → subprocess NOT called with --provider ollama."""
    monkeypatch.delenv("CLINE_PROVIDER", raising=False)
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"done", b"")

    with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        await handle_dispatch_to_cline({"task": "fix bug", "model": "claude-3"})

    args = mock_exec.call_args[0]
    assert "ollama" not in args


# ---------------------------------------------------------------------------
# handle_complete_step — memory write tests
# ---------------------------------------------------------------------------

async def test_complete_step_writes_memory_on_final(monkeypatch):
    """advance_step returns False (final step) → write_context called with memory:directive: key."""
    monkeypatch.setenv("DB_PATH", ":memory:")

    mock_directive = {
        "id": "test-dir-001",
        "title": "Test Directive",
        "description": "Test",
        "steps": [
            {"id": 1, "status": "complete"},
            {"id": 2, "status": "complete"},
        ],
    }

    with patch("duggerbot.mcp.dev_tools.advance_step", return_value=False), \
         patch("duggerbot.mcp.dev_tools.get_active_directive", return_value=mock_directive), \
         patch("duggerbot.mcp.dev_tools.write_context") as mock_write:
        result = await handle_complete_step({"step_id": 2})
        data = json.loads(result[0].text)

    assert data["success"] is True
    assert data["has_more_steps"] is False
    mock_write.assert_called()
    call_args = mock_write.call_args[0]
    assert "memory:directive:test-dir-001:complete" in call_args[0]


async def test_complete_step_no_memory_on_intermediate(monkeypatch):
    """advance_step returns True (more steps) → write_context NOT called with memory: key."""
    monkeypatch.setenv("DB_PATH", ":memory:")

    with patch("duggerbot.mcp.dev_tools.advance_step", return_value=True), \
         patch("duggerbot.mcp.dev_tools.write_context") as mock_write:
        result = await handle_complete_step({"step_id": 1})
        data = json.loads(result[0].text)

    assert data["success"] is True
    assert data["has_more_steps"] is True
    # write_context may be called for directive updates, but not for memory: key
    if mock_write.called:
        for call in mock_write.call_args_list:
            key = call[0][0]
            assert not key.startswith("memory:directive:")
