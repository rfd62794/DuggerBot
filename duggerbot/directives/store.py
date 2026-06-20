"""Directive store — wraps SQLite context store with directive-aware operations.

Keys used:
  directive:active           → full directive JSON
  directive:active:current   → current step number (int)
  directive:active:status    → overall status string
  directive:history:{id}     → completed directive JSON
  memory:directive:{id}:complete → completion summary
"""
import json
import datetime
from duggerbot.context_store import write_context, read_context, delete_context
from duggerbot.directives.schema import Directive, DirectiveStep, StepStatus


DIRECTIVE_ACTIVE_KEY = "directive:active"
DIRECTIVE_CURRENT_KEY = "directive:active:current"
DIRECTIVE_STATUS_KEY = "directive:active:status"


async def write_active_directive(directive: Directive) -> None:
    """Store a new directive, set step 1 as current, status as pending."""
    await write_context(DIRECTIVE_ACTIVE_KEY, json.dumps(directive))
    await write_context(DIRECTIVE_CURRENT_KEY, "1")
    await write_context(DIRECTIVE_STATUS_KEY, "pending")


async def get_active_directive() -> Directive | None:
    """Load the active directive. Returns None if none exists."""
    value = await read_context(DIRECTIVE_ACTIVE_KEY)
    if value is None:
        return None
    return json.loads(value)


async def get_current_step() -> tuple[int, DirectiveStep | None]:
    """Get the current step number and the step itself.
    
    Returns: (step_number, step_dict or None if no active directive)
    """
    directive = await get_active_directive()
    if directive is None:
        return 0, None
    
    current_str = await read_context(DIRECTIVE_CURRENT_KEY)
    if current_str is None:
        current = 1
    else:
        current = int(current_str)
    
    steps = directive.get("steps", [])
    if current < 1 or current > len(steps):
        return current, None
    
    return current, steps[current - 1]


async def advance_step(step_id: int) -> bool:
    """Mark step as complete and advance to next.
    
    Returns: True if there are more steps, False if directive is complete.
    """
    directive = await get_active_directive()
    if directive is None:
        return False
    
    steps = directive.get("steps", [])
    if step_id < 1 or step_id > len(steps):
        return False
    
    # Mark this step complete
    steps[step_id - 1]["status"] = "complete"
    
    # Update directive with modified steps
    directive["steps"] = steps
    await write_context(DIRECTIVE_ACTIVE_KEY, json.dumps(directive))
    
    # Advance pointer
    next_step = step_id + 1
    if next_step > len(steps):
        await write_context(DIRECTIVE_STATUS_KEY, "complete")
        return False
    else:
        await write_context(DIRECTIVE_CURRENT_KEY, str(next_step))
        # Mark next step as in_progress
        steps[next_step - 1]["status"] = "in_progress"
        directive["steps"] = steps
        await write_context(DIRECTIVE_ACTIVE_KEY, json.dumps(directive))
        return True


async def escalate_step(step_id: int, reason: str) -> None:
    """Mark step as escalated, halt directive, write reason."""
    directive = await get_active_directive()
    if directive is None:
        return

    steps = directive.get("steps", [])
    if 1 <= step_id <= len(steps):
        steps[step_id - 1]["status"] = "escalated"
        directive["steps"] = steps
        await write_context(DIRECTIVE_ACTIVE_KEY, json.dumps(directive))

    await write_context(DIRECTIVE_STATUS_KEY, f"escalated:{reason}")


async def _write_completion_memory(directive: Directive) -> None:
    """Write directive completion summary to memory: namespace in context store."""
    directive_id = directive.get("id", "unknown")
    steps = directive.get("steps", [])
    completed = sum(1 for s in steps if s.get("status") == "complete")

    summary = {
        "directive_id": directive_id,
        "title": directive.get("title", ""),
        "description": directive.get("description", ""),
        "steps_completed": completed,
        "total_steps": len(steps),
        "status": "complete",
        "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    await write_context(
        f"memory:directive:{directive_id}:complete",
        json.dumps(summary),
    )


async def archive_directive(directive_id: str) -> None:
    """Move active directive to history, write completion memory, clear active keys."""
    directive = await get_active_directive()
    if directive is None:
        return

    # Write completion memory before archiving
    await _write_completion_memory(directive)

    # Write to history
    history_key = f"directive:history:{directive_id}"
    await write_context(history_key, json.dumps(directive))

    # Clear active keys
    await delete_context(DIRECTIVE_ACTIVE_KEY)
    await delete_context(DIRECTIVE_CURRENT_KEY)
    await delete_context(DIRECTIVE_STATUS_KEY)
