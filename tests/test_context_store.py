"""Tests for duggerbot.context_store — Phase 3.8."""

from unittest.mock import patch

from duggerbot.context_store import (
    delete_context,
    list_context,
    read_context,
    write_context,
)


async def test_write_and_read_context(tmp_path):
    """Write key→value, read back same value."""
    with patch("duggerbot.context_store.DB_PATH", tmp_path / "test_context.db"):
        await write_context("greeting", "hello world")
        result = await read_context("greeting")
        assert result == "hello world"


async def test_read_returns_none_for_missing_key(tmp_path):
    """Read nonexistent key → None."""
    with patch("duggerbot.context_store.DB_PATH", tmp_path / "test_context.db"):
        result = await read_context("nonexistent")
        assert result is None


async def test_write_overwrites_existing_key(tmp_path):
    """Write key twice → second value wins."""
    with patch("duggerbot.context_store.DB_PATH", tmp_path / "test_context.db"):
        await write_context("key", "first")
        await write_context("key", "second")
        result = await read_context("key")
        assert result == "second"


async def test_delete_returns_true_when_key_exists(tmp_path):
    """Delete existing key → True, subsequent read → None."""
    with patch("duggerbot.context_store.DB_PATH", tmp_path / "test_context.db"):
        await write_context("doomed", "value")
        deleted = await delete_context("doomed")
        assert deleted is True
        result = await read_context("doomed")
        assert result is None


async def test_list_context_filters_by_prefix(tmp_path):
    """Write 'a:1', 'a:2', 'b:1' → list('a:') returns ['a:1', 'a:2']."""
    with patch("duggerbot.context_store.DB_PATH", tmp_path / "test_context.db"):
        await write_context("a:1", "v1")
        await write_context("a:2", "v2")
        await write_context("b:1", "v3")
        keys = await list_context("a:")
        assert keys == ["a:1", "a:2"]
