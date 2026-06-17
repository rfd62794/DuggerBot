"""Tests for the directive management system."""
import json
import os
import pytest
from duggerbot.directives import Directive, DirectiveStep, StepStatus, AgentType


from unittest.mock import patch, AsyncMock


@pytest.fixture(autouse=True)
def isolated_context_db(tmp_path, monkeypatch):
    """Ensure all directive tests use isolated temp database."""
    db_path = tmp_path / "test_context.db"
    monkeypatch.setenv("CONTEXT_DB_PATH", str(db_path))
    # Also patch at module level for safety
    monkeypatch.setattr("duggerbot.context_store.DB_PATH", db_path)

# -----------------------------------------------------------------------------
# Step 1: Schema tests (239/0/0 floor)
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# Step 3: MCP tool tests (245/0/0 floor)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_write_directive_returns_step_count():
    """write_directive handler returns step count and directive ID."""
    from duggerbot.mcp.dev_tools import handle_write_directive
    
    directive: Directive = {
        "id": "test-directive-001",
        "title": "Test Directive",
        "description": "A test directive",
        "preflight_floor": "237/0/0",
        "steps": [
            {"id": 1, "title": "Step 1", "files": [], "readonly_files": [],
             "task": "Do step 1", "tests": [], "floor": "239/0/0", "commit": "Done",
             "stop_rules": [], "agent": "devin", "status": "pending"},
            {"id": 2, "title": "Step 2", "files": [], "readonly_files": [],
             "task": "Do step 2", "tests": [], "floor": "242/0/0", "commit": "Done",
             "stop_rules": [], "agent": "devin", "status": "pending"},
        ],
        "created_at": "2024-06-16T00:00:00Z",
        "author": "claude",
    }
    
    with patch("duggerbot.mcp.dev_tools.write_active_directive", new_callable=AsyncMock):
        result = await handle_write_directive({"directive": json.dumps(directive)})
        data = json.loads(result[0].text)
        
        assert data["success"] is True
        assert data["directive_id"] == "test-directive-001"
        assert data["step_count"] == 2
        assert data["current_step"] == 1


@pytest.mark.asyncio
async def test_get_current_step_returns_pending_step():
    """get_current_step handler returns step with pending status."""
    from duggerbot.mcp.dev_tools import handle_get_current_step
    
    step: DirectiveStep = {
        "id": 1, "title": "Current Step", "files": ["file.py"], "readonly_files": [],
        "task": "Do something", "tests": ["test_something"], "floor": "239/0/0",
        "commit": "Done", "stop_rules": ["pytest fails"], "agent": "devin",
        "status": "pending",
    }
    
    with patch("duggerbot.mcp.dev_tools.get_current_step", return_value=(1, step)):
        result = await handle_get_current_step({})
        data = json.loads(result[0].text)
        
        assert data["has_active_directive"] is True
        assert data["step_number"] == 1
        assert data["step"]["title"] == "Current Step"
        assert data["step"]["status"] == "pending"


@pytest.mark.asyncio
async def test_complete_step_advances_pointer():
    """complete_step handler advances to next step."""
    from duggerbot.mcp.dev_tools import handle_complete_step
    
    with patch("duggerbot.mcp.dev_tools.advance_step", return_value=True):
        result = await handle_complete_step({"step_id": 1})
        data = json.loads(result[0].text)
        
        assert data["success"] is True
        assert data["has_more_steps"] is True
        assert data["next_step"] == 2


# -----------------------------------------------------------------------------
# Step 2: Store tests (242/0/0 floor)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_and_read_directive():
    """write_active_directive stores, get_active_directive retrieves."""
    from duggerbot.directives import write_active_directive, get_active_directive
    
    directive: Directive = {
        "id": "test-001",
        "title": "Test Directive",
        "description": "A test",
        "preflight_floor": "237/0/0",
        "steps": [],
        "created_at": "2024-06-16T00:00:00Z",
        "author": "test",
    }
    
    with patch("duggerbot.directives.store.write_context", new_callable=AsyncMock) as mock_write:
        await write_active_directive(directive)
        # Should write 3 keys
        assert mock_write.call_count == 3


@pytest.mark.asyncio
async def test_advance_step_increments_pointer():
    """advance_step marks step complete and moves to next."""
    from duggerbot.directives import advance_step, get_active_directive
    
    step1: DirectiveStep = {
        "id": 1, "title": "Step 1", "files": [], "readonly_files": [],
        "task": "Do step 1", "tests": [], "floor": "239/0/0", "commit": "Done",
        "stop_rules": [], "agent": "devin", "status": "in_progress",
    }
    step2: DirectiveStep = {
        "id": 2, "title": "Step 2", "files": [], "readonly_files": [],
        "task": "Do step 2", "tests": [], "floor": "242/0/0", "commit": "Done",
        "stop_rules": [], "agent": "devin", "status": "pending",
    }
    directive: Directive = {
        "id": "test-002",
        "title": "Test",
        "description": "Test",
        "preflight_floor": "237/0/0",
        "steps": [step1, step2],
        "created_at": "2024-06-16T00:00:00Z",
        "author": "test",
    }
    
    with patch("duggerbot.directives.store.read_context", return_value=json.dumps(directive)), \
         patch("duggerbot.directives.store.write_context", new_callable=AsyncMock) as mock_write:
        
        result = await advance_step(1)
        assert result is True  # More steps remain


@pytest.mark.asyncio
async def test_escalate_marks_step_status():
    """escalate_step marks step escalated and halts directive."""
    from duggerbot.directives import escalate_step
    
    step1: DirectiveStep = {
        "id": 1, "title": "Step 1", "files": [], "readonly_files": [],
        "task": "Do step 1", "tests": [], "floor": "239/0/0", "commit": "Done",
        "stop_rules": [], "agent": "devin", "status": "in_progress",
    }
    directive: Directive = {
        "id": "test-003",
        "title": "Test",
        "description": "Test",
        "preflight_floor": "237/0/0",
        "steps": [step1],
        "created_at": "2024-06-16T00:00:00Z",
        "author": "test",
    }
    
    with patch("duggerbot.directives.store.read_context", return_value=json.dumps(directive)), \
         patch("duggerbot.directives.store.write_context", new_callable=AsyncMock) as mock_write:
        
        await escalate_step(1, "pytest failed")
        # Should update directive and status
        assert mock_write.call_count >= 2


# -----------------------------------------------------------------------------
# Step 1: Schema tests (239/0/0 floor)
# -----------------------------------------------------------------------------

def test_directive_step_has_required_fields():
    """DirectiveStep TypedDict accepts all required fields."""
    step: DirectiveStep = {
        "id": 1,
        "title": "Test step",
        "files": ["file.py"],
        "readonly_files": ["readonly.py"],
        "task": "Do something",
        "tests": ["test_something"],
        "floor": "239/0/0",
        "commit": "Test commit",
        "stop_rules": ["pytest fails"],
        "agent": "devin",
        "status": "pending",
    }
    assert step["id"] == 1
    assert step["title"] == "Test step"
    assert step["files"] == ["file.py"]
    assert step["status"] == "pending"


def test_directive_has_required_fields():
    """Directive TypedDict accepts all required fields."""
    step: DirectiveStep = {
        "id": 1,
        "title": "Step 1",
        "files": [],
        "readonly_files": [],
        "task": "Do step 1",
        "tests": [],
        "floor": "239/0/0",
        "commit": "Step 1 done",
        "stop_rules": [],
        "agent": "cline",
        "status": "pending",
    }
    directive: Directive = {
        "id": "2024-06-16-directive-001",
        "title": "Test Directive",
        "description": "A test directive",
        "preflight_floor": "237/0/0",
        "steps": [step],
        "created_at": "2024-06-16T00:00:00Z",
        "author": "claude",
    }
    assert directive["id"] == "2024-06-16-directive-001"
    assert directive["title"] == "Test Directive"
    assert len(directive["steps"]) == 1
    assert directive["preflight_floor"] == "237/0/0"


def test_step_status_literals():
    """StepStatus accepts all valid literal values."""
    statuses: list[StepStatus] = ["pending", "in_progress", "complete", "failed", "escalated"]
    for status in statuses:
        step: DirectiveStep = {
            "id": 1, "title": "Test", "files": [], "readonly_files": [],
            "task": "Test", "tests": [], "floor": "239/0/0", "commit": "Test",
            "stop_rules": [], "agent": "auto", "status": status,
        }
        assert step["status"] == status


def test_agent_type_literals():
    """AgentType accepts all valid literal values."""
    agents: list[AgentType] = ["devin", "cline", "auto"]
    for agent in agents:
        step: DirectiveStep = {
            "id": 1, "title": "Test", "files": [], "readonly_files": [],
            "task": "Test", "tests": [], "floor": "239/0/0", "commit": "Test",
            "stop_rules": [], "agent": agent, "status": "pending",
        }
        assert step["agent"] == agent
