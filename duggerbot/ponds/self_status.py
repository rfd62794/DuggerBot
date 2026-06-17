"""Self-status pond — TOBOR's own health check.

Calls TOBOR's internal functions directly (no HTTP).
Returns version, test floor, open issues.
No credentials required.
"""
import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

POND_NAME = "self_status"


def _read_open_issues() -> list[str]:
    """Read open issues from docs/issues/ directory."""
    issues_dir = Path("docs/issues")
    if not issues_dir.exists():
        return []
    issues = []
    for f in sorted(issues_dir.glob("ISSUE-*.md")):
        content = f.read_text(encoding="utf-8")
        # Status line: look for "open" (case-insensitive)
        first_lines = content[:500].lower()
        if "resolved" in first_lines or "closed" in first_lines:
            continue
        # Title: first H1 line
        for line in content.splitlines():
            if line.startswith("# "):
                issues.append(line[2:].strip())
                break
    return issues


async def run() -> dict:
    """Run self-status pond — TOBOR health check."""
    try:
        from duggerbot.version import get_version_string
        version = get_version_string()
    except Exception as e:
        version = f"unknown ({e})"

    try:
        repo_root = Path(__file__).parent.parent.parent
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=no", "-q"],
            capture_output=True, text=True,
            cwd=repo_root
        )
        last_line = result.stdout.strip().split("\n")[-1]
        floor = last_line
    except Exception as e:
        floor = f"unknown ({e})"

    issues = _read_open_issues()

    summary_lines = [
        f"🤖 <b>TOBOR Morning Status</b>",
        f"",
        f"🔖 Version: {version}",
        f"✅ Tests: {floor}",
    ]
    if issues:
        summary_lines.append(f"📋 Open Issues ({len(issues)}):")
        for issue in issues[:5]:  # cap at 5
            summary_lines.append(f"   • {issue}")
    else:
        summary_lines.append("📋 Open Issues: none")

    summary_lines.append("")
    summary_lines.append("Next: Phase 4b — Google credentials + ponds")

    return {
        "pond": POND_NAME,
        "version": version,
        "floor": floor,
        "open_issues": issues,
        "summary": "\n".join(summary_lines),
        "error": None,
    }
