# ISSUE-004: Deployment scripts gitignored — never committed

## Status
RESOLVED

## Problem
`scripts/*.ps1` in `.gitignore` caused `initialize.ps1` (Phase 3.6) and
`nssm_deploy.ps1` to be excluded from the repo. Both are deployment-critical:
`initialize.ps1` is the only bootstrap path for new instances (ADR-009), and
without it Tower gets nothing on `git pull`.

## Root Cause
The blanket glob `scripts/*.ps1` was added to keep private/one-off scripts out
of the repo, but it caught deployment scripts too.

## Fix
Added negation rules to `.gitignore`:
```
scripts/*.ps1
!scripts/initialize.ps1
!scripts/nssm_deploy.ps1
```

Git negation rules (`!`) exempt specific files from a preceding glob match.

## Found
Phase 3.7 — before Part B manual deployment verification.

## Impact
Without this fix, `initialize.ps1` exists on Nitro 5 but does not travel to
Tower on `git pull`. Tower deployment would require manual file copy, defeating
the purpose of the Initializer.
