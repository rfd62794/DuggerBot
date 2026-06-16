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
    handle_get_migration_manifest,
    handle_get_open_issues,
    handle_get_project_state,
    handle_verify_test_floor,
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
