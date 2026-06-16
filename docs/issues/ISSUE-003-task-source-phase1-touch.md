**ISSUE-003: `task_source` field added to Phase 1 `TaskRequest`**

**Created by:** Phase 3 implementation
**Severity:** Low
**Must close:** Before Phase 4 certifies
**Touches:** `duggerbot/router/models.py`

**Problem:**
Phase 3 added `task_source: str | None = None` to `TaskRequest` in `router/models.py` — a Phase 1 file that was nominally locked. The field is required by `TwinCoordinator.should_delegate_to_remote()` to distinguish scheduled tasks from on-demand tasks.

The change is a one-liner, optional with a None default, and breaks nothing. All 149 tests pass. But it's technical debt of the "touched a locked file" variety and should be acknowledged.

**Resolution:**
No code change needed. Acknowledge the touch in Phase 4 pre-flight and confirm no Phase 1 test regressions. If `task_source` needs to become an enum or gain validation, do it in Phase 4 when RALPH actually populates the field.
