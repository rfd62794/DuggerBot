"""Directive schema — TypedDict definitions for structured agent directives.

A directive is a multi-step task plan that agents execute sequentially.
Each step has a floor (test count), file constraints, and stop rules.
"""
from typing import TypedDict, Literal


StepStatus = Literal["pending", "in_progress", "complete", "failed", "escalated"]
AgentType = Literal["devin", "cline", "auto"]


class DirectiveStep(TypedDict):
    """A single step in a directive — one agent, one task, one floor."""
    id: int                          # Step number (1-indexed)
    title: str                       # Human-readable step name
    files: list[str]                 # Files the agent MAY touch
    readonly_files: list[str]        # Files explicitly locked (read-only)
    task: str                        # What to do (detailed instruction)
    tests: list[str]                 # Test names to write for this step
    floor: str                       # Expected test count: "239/0/0"
    commit: str                      # Exact commit message when step completes
    stop_rules: list[str]            # When to halt (e.g., "pytest fails")
    agent: AgentType                 # Which agent should execute this step
    status: StepStatus               # Current status


class Directive(TypedDict):
    """A complete multi-step directive — the contract between Claude and agents."""
    id: str                          # Unique directive ID (timestamp-based)
    title: str                       # Directive title
    description: str                 # What this directive accomplishes
    preflight_floor: str             # Required test count before starting: "237/0/0"
    steps: list[DirectiveStep]       # Ordered list of steps
    created_at: str                  # ISO timestamp
    author: str                      # Who wrote the directive (e.g., "claude")
