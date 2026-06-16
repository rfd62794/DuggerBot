"""Tests for duggerbot.main — Phase 3.7."""

import logging
from unittest.mock import MagicMock, patch


def test_load_dotenv_called_with_override_false():
    """load_dotenv called with .env.local and override=False — not True."""
    with patch("duggerbot.main.load_dotenv") as mock_dotenv, \
         patch("duggerbot.main.uvicorn.run"), \
         patch("duggerbot.main.logging.basicConfig"), \
         patch("duggerbot.main.logging.FileHandler", return_value=MagicMock()):
        from duggerbot.main import main
        main()
        mock_dotenv.assert_called_once_with(".env.local", override=False)


def test_uvicorn_run_uses_MCP_PORT_env(monkeypatch):
    """MCP_PORT=9000 in env → uvicorn called with port=9000."""
    monkeypatch.setenv("MCP_PORT", "9000")
    with patch("duggerbot.main.load_dotenv"), \
         patch("duggerbot.main.uvicorn.run") as mock_run, \
         patch("duggerbot.main.logging.basicConfig"), \
         patch("duggerbot.main.logging.FileHandler", return_value=MagicMock()):
        from duggerbot.main import main
        main()
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["port"] == 9000


def test_uvicorn_run_defaults_port_8001(monkeypatch):
    """No MCP_PORT → uvicorn called with port=8001."""
    monkeypatch.delenv("MCP_PORT", raising=False)
    with patch("duggerbot.main.load_dotenv"), \
         patch("duggerbot.main.uvicorn.run") as mock_run, \
         patch("duggerbot.main.logging.basicConfig"), \
         patch("duggerbot.main.logging.FileHandler", return_value=MagicMock()):
        from duggerbot.main import main
        main()
        mock_run.assert_called_once()
        assert mock_run.call_args.kwargs["port"] == 8001


def test_logging_configured_with_stream_and_file_handler():
    """basicConfig called with handlers containing both StreamHandler and FileHandler."""
    mock_file_handler = MagicMock()
    with patch("duggerbot.main.load_dotenv"), \
         patch("duggerbot.main.uvicorn.run"), \
         patch("duggerbot.main.logging.FileHandler", return_value=mock_file_handler), \
         patch("duggerbot.main.logging.basicConfig") as mock_basic, \
         patch("duggerbot.main.Path.mkdir"):
        from duggerbot.main import _configure_logging
        _configure_logging()
        mock_basic.assert_called_once()
        handlers = mock_basic.call_args.kwargs["handlers"]
        handler_types = [type(h).__name__ for h in handlers]
        assert "StreamHandler" in handler_types
        assert "MagicMock" in handler_types  # FileHandler was mocked
