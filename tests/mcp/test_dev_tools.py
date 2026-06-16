"""Tests for duggerbot.mcp.dev_tools — Phase 3.5."""

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from duggerbot.mcp.dev_tools import (
    DEV_TOOL_HANDLERS,
    _parse_pytest_summary,
    _run_command,
    handle_check_coverage,
    handle_check_for_update,
    handle_delete_context,
    handle_dispatch_to_cline,
    handle_get_migration_manifest,
    handle_get_open_issues,
    handle_get_project_state,
    handle_get_version,
    handle_list_context,
    handle_read_context,
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


async def test_handle_dispatch_to_cline_returns_output():
    """Stub handler returns success=False with CLI not installed message."""
    result = await handle_dispatch_to_cline({"task": "fix the bug", "model": "ollama/qwen3"})
    data = json.loads(result[0].text)
    assert data["success"] is False
    assert data["model"] == "ollama/qwen3"
    assert "not installed" in data["output"]
