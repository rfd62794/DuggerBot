"""Tests for duggerbot.telegram — Phase 4a."""

from unittest.mock import AsyncMock, patch

from duggerbot.telegram import send_message


async def test_send_message_returns_true_on_success():
    """Mock httpx returns 200 → send_message() returns True."""
    from unittest.mock import Mock
    mock_response = AsyncMock()
    mock_response.raise_for_status = Mock()  # raise_for_status is sync

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("duggerbot.telegram.httpx.AsyncClient", return_value=mock_client):
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test_token",
            "TELEGRAM_CHAT_ID": "123456"
        }):
            result = await send_message("Test message")
            assert result is True


async def test_send_message_returns_false_when_token_missing():
    """No TELEGRAM_BOT_TOKEN env var → returns False without calling httpx."""
    with patch("duggerbot.telegram.httpx.AsyncClient") as mock_client_class:
        with patch.dict("os.environ", {}, clear=True):
            result = await send_message("Test message")
            assert result is False
            mock_client_class.assert_not_called()
