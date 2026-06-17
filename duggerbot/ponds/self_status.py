"""Morning dispatch assembler — runs all ponds, builds daily briefing."""
import logging
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from duggerbot.ponds.youtube import run as youtube_run
from duggerbot.ponds.calendar import run as calendar_run
from duggerbot.ponds.blog import run as blog_run
from duggerbot.ponds.devto import run as devto_run

log = logging.getLogger(__name__)
POND_NAME = "morning_dispatch"


def _get_floor() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "--tb=no", "-q"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        return result.stdout.strip().split("\n")[-1]
    except Exception as e:
        return f"unknown ({e})"


def _get_open_issues() -> list[str]:
    issues_dir = Path("docs/issues")
    if not issues_dir.exists():
        return []
    issues = []
    for f in sorted(issues_dir.glob("ISSUE-*.md")):
        content = f.read_text(encoding="utf-8")
        if "resolved" in content[:500].lower() or "closed" in content[:500].lower():
            continue
        for line in content.splitlines():
            if line.startswith("# "):
                issues.append(line[2:].strip())
                break
    return issues


async def run() -> dict:
    """Run all ponds and assemble morning briefing."""
    from duggerbot.version import get_version_string

    date_str = datetime.now(timezone.utc).strftime("%b %d")
    version = get_version_string()
    floor = _get_floor()
    issues = _get_open_issues()

    # Header
    sections = [
        f"🤖 <b>TOBOR Morning Status</b> — {date_str}",
        f"🔖 {version} | ✅ {floor}",
    ]

    # Run ponds — collect summaries, never raise
    for pond_fn in [youtube_run, calendar_run, blog_run, devto_run]:
        try:
            result = await pond_fn()
            if result.get("summary"):
                sections.append("")
                sections.append(result["summary"])
        except Exception as e:
            log.error("Pond %s failed in morning dispatch: %s", pond_fn.__name__, e)

    # Issues
    if issues:
        sections.append("")
        issue_names = " • ".join(i.split(":")[0] for i in issues[:5])
        sections.append(f"📋 Open Issues ({len(issues)}): {issue_names}")

    summary = "\n".join(sections)

    return {
        "pond": POND_NAME,
        "version": version,
        "floor": floor,
        "summary": summary,
        "error": None,
    }
