# ISSUE-006: NSSM service cannot authenticate git fetch

## Status
OPEN

## Problem
The background update check (`_update_check_loop` in server.py) calls
`git fetch origin main` via `get_remote_revision()`. NSSM runs as LocalSystem,
which has no access to the Windows Credential Manager where git credentials are
stored. The fetch fails silently — `get_remote_revision()` returns 0, update
appears unavailable, self-update never triggers.

The code is correct. The deployment environment blocks it.

## Symptom
`check_for_update()` always returns `update_available: false` even when
origin/main is ahead, because `get_remote_revision()` returns 0 on auth failure.

## Verification
From admin shell, simulate the service account:
```powershell
C:\Windows\System32\runas /user:SYSTEM "C:\Program Files\Git\cmd\git.exe fetch origin main"
```
If auth error → confirmed.

## Fix Options

### Option A — Embed PAT in remote URL (recommended, fast)
```powershell
git remote set-url origin https://<GITHUB_PAT>@github.com/rfd62794/DuggerBot.git
```
Requires a GitHub Personal Access Token with `repo` read scope.
PAT is stored in the repo's `.git/config` — local only, never committed.

### Option B — Configure credential manager for LocalSystem
Requires group policy changes or logging in as the service account to
populate Windows Credential Manager. More complex, no clear benefit over A.

### Option C — Change NSSM ObjectName to user account
Service inherits user's credential store. Tradeoff: requires user to have
"Log on as a service" policy, and credentials are tied to that user.

## Priority
Medium — blocks self-update from working. Manual `git pull` + service restart
is the workaround until fixed. Not blocking Phase 4 development, but should
be resolved before Tower deployment.

## Related
- ISSUE-005: NSSM PATH missing git/uv (same root cause: LocalSystem limitations)
- ADR-009: Version tracking and update protocol
- Phase 3.6: `_update_check_loop` in server.py

## Found
Phase 3.7 Part B — deployment verification identified the gap.
