"""Tests for duggerbot.directives.store — directive persistence and completion memory."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from duggerbot.directives.store import (
    archive_directive,
    write_active_directive,
    get_active_directive,
    _write_completion_memory,
)


@pytest.fixture
async def clean_store(tmp_path, monkeypatch):
    """Use temporary database for isolation."""
    db_path = tmp_path / "test_directive.db"
    monkeypatch.setattr("duggerbot.context_store.DB_PATH", db_path)
    yield
    # Cleanup happens automatically with tmp_path


# ---------------------------------------------------------------------------
# Completion memory tests
# ---------------------------------------------------------------------------

async def test_archive_writes_completion_memory(clean_store):
    """archive_directive called → context store has memory:directive:{id}:complete key."""
    directive = {
        "id": "test-dir-001",
        "title": "Test Directive",
        "description": "Test completion memory",
        "steps": [
            {"id": 1, "status": "complete"},
            {"id": 2, "status": "complete"},
        ],
    }
    await write_active_directive(directive)

    from duggerbot.context_store import list_context
    before_keys = await list_context("memory:")
    assert len(before_keys) == 0  # No memory keys before

    await archive_directive("test-dir-001")

    after_keys = await list_context("memory:")
    assert len(after_keys) == 1
    assert "memory:directive:test-dir-001:complete" in after_keys


async def test_completion_memory_format(clean_store):
    """Memory value is valid JSON with directive_id, title, steps_completed, completed_at."""
    directive = {
        "id": "test-dir-002",
        "title": "Format Test",
        "description": "Test JSON structure",
        "steps": [
            {"id": 1, "status": "complete"},
            {"id": 2, "status": "complete"},
            {"id": 3, "status": "pending"},
        ],
    }
    await write_active_directive(directive)
    await archive_directive("test-dir-002")

    from duggerbot.context_store import read_context
    memory_value = await read_context("memory:directive:test-dir-002:complete")
    assert memory_value is not None

    data = json.loads(memory_value)
    assert data["directive_id"] == "test-dir-002"
    assert data["title"] == "Format Test"
    assert data["steps_completed"] == 2
    assert data["total_steps"] == 3
    assert data["status"] == "complete"
    assert "completed_at" in data
    # ISO format with UTC (either Z or +00:00)
    assert data["completed_at"].endswith("Z") or "+00:00" in data["completed_at"]
