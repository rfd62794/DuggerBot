"""Tests for duggerbot.ponds — Phase 4a."""

from pathlib import Path
from unittest.mock import patch

from duggerbot.ponds import self_status


async def test_self_status_returns_pond_name(tmp_path):
    """Run self_status.run() with mocked subprocess → result["pond"] == "self_status"."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r50"):
            # No issues dir
            result = await self_status.run()
            assert result["pond"] == "self_status"


async def test_self_status_summary_contains_version(tmp_path):
    """Mocked get_version_string → summary contains version string."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r99"):
            result = await self_status.run()
            assert "0.1.0.r99" in result["summary"]


async def test_self_status_no_issues_when_dir_empty(tmp_path, monkeypatch):
    """Empty tmp_path issues dir → open_issues == []."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r50"):
            # Monkeypatch the issues dir to a temp empty dir
            issues_dir = tmp_path / "issues"
            issues_dir.mkdir()
            with patch.object(Path, "glob", lambda self, pattern: [] if "ISSUE-*.md" in pattern else Path.glob(self, pattern)):
                with patch.object(Path, "exists", lambda self: False if str(self).endswith("docs/issues") else Path.exists(self)):
                    result = await self_status.run()
                    assert result["open_issues"] == []
