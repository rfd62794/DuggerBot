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


async def test_self_status_no_issues_when_dir_empty(tmp_path):
    """No issues in docs/issues → open_issues == []."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = "200 passed in 1.5s"
        mock_run.return_value.stderr = ""
        with patch("duggerbot.version.get_version_string", return_value="0.1.0.r50"):
            with patch("duggerbot.ponds.self_status._read_open_issues", return_value=[]):
                result = await self_status.run()
                assert result["open_issues"] == []
