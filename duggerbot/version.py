"""Version tracking and self-update protocol per ADR-009."""

import os
import subprocess
from pathlib import Path

# Semantic version — bump these manually on breaking changes
MAJOR = 0
MINOR = 1
PATCH = 0


def _run_git(*args: str) -> tuple[int, str]:
    """Run a git command. Returns (returncode, stdout.strip())."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,  # repo root
    )
    return result.returncode, result.stdout.strip()


def get_revision() -> int:
    """Return git commit count on HEAD. Returns 0 if git unavailable."""
    try:
        from duggerbot._version_info import REVISION
        return REVISION
    except ImportError:
        pass
    code, out = _run_git("rev-list", "--count", "HEAD")
    return int(out) if code == 0 and out.isdigit() else 0


def get_remote_revision() -> int:
    """
    Fetch from origin and return remote commit count on main.
    Returns 0 if fetch fails or git unavailable.
    Performs a network call (git fetch) — do not call from hot paths.
    """
    _run_git("fetch", "origin", "main")
    code, out = _run_git("rev-list", "--count", "origin/main")
    return int(out) if code == 0 and out.isdigit() else 0


def get_version_string() -> str:
    """Return full version string: MAJOR.MINOR.PATCH.rN"""
    return f"{MAJOR}.{MINOR}.{PATCH}.r{get_revision()}"


def get_git_hash() -> str:
    """Return short git commit hash for debugging. Returns 'unknown' on failure."""
    code, out = _run_git("rev-parse", "--short", "HEAD")
    return out if code == 0 else "unknown"


def is_update_available() -> bool:
    """
    True if origin/main has more commits than local HEAD.
    Performs git fetch — network call, may be slow.
    """
    remote = get_remote_revision()
    local = get_revision()
    return remote > local and remote > 0


def pull_update() -> bool:
    """
    Run git pull origin main.
    Returns True on success, False on any failure.
    Does NOT exit — caller decides exit code.
    """
    code, _ = _run_git("pull", "origin", "main")
    return code == 0


def apply_update_and_exit() -> None:
    """
    Pull and exit with appropriate code for NSSM recovery:
    - Exit 0: pull succeeded → NSSM will restart with new version
    - Exit 1: pull failed → NSSM will stop (no restart loop)
    Uses os._exit() — bypasses Python cleanup. Intentional per ADR-009.
    """
    if pull_update():
        os._exit(0)
    else:
        os._exit(1)
