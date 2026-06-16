# ISSUE-005: NSSM service PATH missing git and uv

## Status
OPEN

## Problem
NSSM runs DuggerBot as `LocalSystem`, which has a minimal PATH. `git` and `uv`
are not in the service account's PATH, so:
- `get_revision()` returns 0 (cosmetic — version reads as `0.1.0.r0`)
- `get_remote_revision()` silently fails (update check never detects updates)

## Symptom
`/health` returns `"version": "0.1.0.r0"` despite the repo having 170+ commits.

## Fix
Add git and uv paths to NSSM's `AppEnvironmentExtra`:

```powershell
$gitPath = "C:\Program Files\Git\cmd"
$uvPath  = (Split-Path (Get-Command uv).Source)
nssm set DuggerBot AppEnvironmentExtra "PYTHONUNBUFFERED=1" "PATH=$gitPath;$uvPath;%PATH%"
```

Alternatively, change NSSM `ObjectName` from `LocalSystem` to the user account,
which inherits the user's full PATH. Tradeoff: service then requires the user to
be logged in (unless configured with "Log on as a service" policy).

## Priority
Low — cosmetic. Version tracking works, revision just reads as 0.
The self-update mechanism (`git fetch`, `git pull`) also won't work until this
is fixed, but manual updates via `git pull` + service restart are fine for now.

## Found
Phase 3.7 Part B — NSSM service health check returned `r0`.

## Confirmed
`C:\Program Files\Git\cmd\git.exe` exists on Nitro 5.
