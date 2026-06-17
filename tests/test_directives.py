"""Tests for the directive management system."""
import pytest
from duggerbot.directives.schema import Directive, DirectiveStep, StepStatus, AgentType


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
