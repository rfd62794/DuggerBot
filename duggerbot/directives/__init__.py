"""Directive management system for multi-agent orchestration.

Claude writes structured directives → TOBOR stores → Devin/Cline execute step-by-step.
"""
from duggerbot.directives.schema import (
    Directive,
    DirectiveStep,
    StepStatus,
    AgentType,
)
from duggerbot.directives.store import (
    write_active_directive,
    get_active_directive,
    get_current_step,
    advance_step,
    escalate_step,
    archive_directive,
)

__all__ = [
    "Directive",
    "DirectiveStep", 
    "StepStatus",
    "AgentType",
    "write_active_directive",
    "get_active_directive",
    "get_current_step",
    "advance_step",
    "escalate_step",
    "archive_directive",
]
