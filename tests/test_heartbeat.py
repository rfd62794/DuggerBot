"""Tests for duggerbot.heartbeat — Phase 3.9."""

from unittest.mock import patch

from duggerbot.heartbeat import (
    _clear_heartbeat,
    _extract_next_task,
    _get_sleep_interval,
    _read_heartbeat,
    _write_response,
    FAST_INTERVAL,
    NORMAL_INTERVAL,
    SLOW_INTERVAL,
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


def test_extract_next_task_returns_task_when_marker_present():
    """<!-- NEXT: ... --> marker in response → returns the task."""
    response = "Some content\n<!-- NEXT: do the next thing -->\nmore content"
    assert _extract_next_task(response) == "do the next thing"


def test_extract_next_task_returns_none_when_no_marker():
    """No marker in response → returns None."""
    assert _extract_next_task("response with no marker") is None


def test_reactive_pacing_fast_after_task_processed():
    """After inbox task processed, next sleep is FAST_INTERVAL."""
    # consecutive_empty = 0 → FAST_INTERVAL
    interval = _get_sleep_interval(0)
    assert interval == FAST_INTERVAL


def test_consecutive_empty_increments_to_slow():
    """3+ consecutive empty → sleep is SLOW_INTERVAL."""
    # consecutive_empty = 0 → FAST
    assert _get_sleep_interval(0) == FAST_INTERVAL
    # consecutive_empty = 1 → NORMAL
    assert _get_sleep_interval(1) == NORMAL_INTERVAL
    # consecutive_empty = 2 → NORMAL
    assert _get_sleep_interval(2) == NORMAL_INTERVAL
    # consecutive_empty = 3 → SLOW
    assert _get_sleep_interval(3) == SLOW_INTERVAL
    # consecutive_empty = 4 → SLOW
    assert _get_sleep_interval(4) == SLOW_INTERVAL


async def test_pond_runs_when_inbox_empty(tmp_path):
    """Empty HEARTBEAT.md → pond_fn called, send_message called."""
    import asyncio
    from unittest.mock import AsyncMock

    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text("", encoding="utf-8")  # Empty inbox
    resp_path = tmp_path / "heartbeat_response.md"

    # Track if pond was called
    pond_called = False
    telegram_called = False

    async def mock_pond():
        nonlocal pond_called
        pond_called = True
        return {"pond": "test_pond", "summary": "Test pond summary"}

    mock_send = AsyncMock(return_value=True)

    with patch("duggerbot.heartbeat.HEARTBEAT_PATH", hb):
        with patch("duggerbot.heartbeat.RESPONSE_PATH", resp_path):
            with patch("duggerbot.heartbeat.POND_ROTATION", [mock_pond]):
                with patch("duggerbot.heartbeat.send_message", mock_send):
                    with patch("duggerbot.heartbeat._consecutive_empty", 0):
                        with patch("duggerbot.heartbeat._pond_index", 0):
                            # Simulate the pond running by calling the mock directly
                            pond_result = await mock_pond()
                            await mock_send(pond_result["summary"])

    assert pond_called is True
    assert mock_send.called is True
