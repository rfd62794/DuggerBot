"""Phase 0: PrivyBot DB audit + migration.

Runs against PrivyBot's SQLite database and produces a structured migration report.

IMPORTANT: Before running, verify PrivyBot's actual table names match:
  - tool_calls
  - api_calls
  - ralph_tasks

If table names differ, update the queries below.

Usage:
    uv run python scripts/migrate_privybot.py --db-path /path/to/privybot.db
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def get_tool_utilization(cursor: sqlite3.Cursor) -> list[dict]:
    """Tool utilization report — which tools were actually used."""
    cursor.execute("""
        SELECT tool_name, COUNT(*) as call_count,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count
        FROM tool_calls
        GROUP BY tool_name
        ORDER BY call_count DESC;
    """)
    return [
        {"tool_name": row[0], "call_count": row[1], "success_count": row[2]}
        for row in cursor.fetchall()
    ]


def get_provider_cost_history(cursor: sqlite3.Cursor) -> list[dict]:
    """Provider cost history — spend per provider per day."""
    cursor.execute("""
        SELECT provider, SUM(cost_usd) as total_cost, COUNT(*) as call_count,
               DATE(created_at) as date
        FROM api_calls
        GROUP BY provider, DATE(created_at)
        ORDER BY date DESC;
    """)
    return [
        {"provider": row[0], "total_cost": row[1], "call_count": row[2], "date": row[3]}
        for row in cursor.fetchall()
    ]


def get_ralph_outputs(cursor: sqlite3.Cursor) -> list[dict]:
    """RALPH research outputs — completed tasks for MEMORY.md seeding."""
    cursor.execute("""
        SELECT task_id, task_type, result_summary, created_at
        FROM ralph_tasks
        WHERE status = 'completed'
        ORDER BY created_at DESC
        LIMIT 50;
    """)
    return [
        {"task_id": row[0], "task_type": row[1], "result_summary": row[2], "created_at": row[3]}
        for row in cursor.fetchall()
    ]


def build_migration_manifest(
    tools: list[dict],
    costs: list[dict],
    ralph_outputs: list[dict],
) -> dict:
    """Build the migration manifest from audit data."""
    migrate_tools = [t for t in tools if t["call_count"] > 0]
    skip_tools = [t for t in tools if t["call_count"] == 0]

    return {
        "generated_at": datetime.now().isoformat(),
        "source": "PrivyBot",
        "target": "DuggerBot",
        "tools": {
            "migrate": [t["tool_name"] for t in migrate_tools],
            "skip": [t["tool_name"] for t in skip_tools],
            "total_migrating": len(migrate_tools),
            "total_skipping": len(skip_tools),
        },
        "cost_history": costs,
        "ralph_outputs_for_memory_seed": ralph_outputs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PrivyBot migration audit")
    parser.add_argument("--db-path", required=True, help="Path to PrivyBot's SQLite database")
    parser.add_argument("--output", default="migration_manifest.json", help="Output manifest path")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    print("Running PrivyBot migration audit...")

    try:
        tools = get_tool_utilization(cursor)
        print(f"  Tools found: {len(tools)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: tool_calls query failed: {e}", file=sys.stderr)
        tools = []

    try:
        costs = get_provider_cost_history(cursor)
        print(f"  Cost records found: {len(costs)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: api_calls query failed: {e}", file=sys.stderr)
        costs = []

    try:
        ralph_outputs = get_ralph_outputs(cursor)
        print(f"  RALPH outputs found: {len(ralph_outputs)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: ralph_tasks query failed: {e}", file=sys.stderr)
        ralph_outputs = []

    conn.close()

    manifest = build_migration_manifest(tools, costs, ralph_outputs)

    output_path = Path(args.output)
    output_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nMigration manifest written to: {output_path}")
    print(f"  Tools to migrate: {manifest['tools']['total_migrating']}")
    print(f"  Tools to skip: {manifest['tools']['total_skipping']}")


if __name__ == "__main__":
    main()
