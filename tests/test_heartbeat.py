"""Tests for duggerbot.heartbeat — Phase 3.9."""

from unittest.mock import patch

from duggerbot.heartbeat import (
    _clear_heartbeat,
    _read_heartbeat,
    _write_response,
    HEARTBEAT_PATH,
    RESPONSE_PATH,
)


def test_read_heartbeat_returns_none_when_empty(tmp_path):
    """HEARTBEAT.md exists but is empty → returns None."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("", encoding="utf-8")
    with patch("duggerbot.heartbeat.HEARTBEAT_PATH", hb):
        assert _read_heartbeat() is None


def test_read_heartbeat_returns_content_when_present(tmp_path):
    """HEARTBEAT.md contains a task → returns stripped content."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("  Research quantum computing trends  \n", encoding="utf-8")
    with patch("duggerbot.heartbeat.HEARTBEAT_PATH", hb):
        result = _read_heartbeat()
        assert result == "Research quantum computing trends"


def test_write_response_creates_file_with_task_and_response(tmp_path):
    """_write_response creates file with task, response, and timestamp."""
    resp_path = tmp_path / "heartbeat_response.md"
    with patch("duggerbot.heartbeat.RESPONSE_PATH", resp_path):
        _write_response("What is TOBOR?", "TOBOR is a personal AI agent.")
    content = resp_path.read_text(encoding="utf-8")
    assert "What is TOBOR?" in content
    assert "TOBOR is a personal AI agent." in content
    assert "Processed:" in content


def test_clear_heartbeat_empties_file(tmp_path):
    """_clear_heartbeat writes empty string to HEARTBEAT.md."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("Some pending task", encoding="utf-8")
    with patch("duggerbot.heartbeat.HEARTBEAT_PATH", hb):
        _clear_heartbeat()
    assert hb.read_text(encoding="utf-8") == ""
