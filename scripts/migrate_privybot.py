"""Phase 0: PrivyBot DB audit + migration.

Runs against PrivyBot's SQLite database and produces a structured migration report.

PrivyBot actual schema (verified 2026-06-15 against stale Nitro 5 copy):
  - agent_actions: task execution log (task_name, ran_at, result, duration_ms)
  - tool_cache: tool call cache (tool_name, params_hash, result, fetched_at)
  - model_usage: per-call cost tracking (model_id, provider, tokens_in/out, cost_usd)
  - budget_tracking: daily budget snapshots (provider, model_id, daily_spent_usd)
  - task_queue: task dispatch (task_name, status, result, duration_ms)
  - memory: curated memory entries (key, content, layer)
  - poll_log: polling history (poll_key, polled_at, success)

NOTE: This was run against the stale Nitro 5 copy of privy.db.
      Re-run against Tower's live DB for the authoritative migration manifest.

Usage:
    python scripts/migrate_privybot.py --db-path C:\\Github\\PrivyBot\\privy.db
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def get_tool_utilization(cursor: sqlite3.Cursor) -> list[dict]:
    """Tool utilization from agent_actions — which tasks actually ran."""
    cursor.execute("""
        SELECT task_name, COUNT(*) as call_count,
               SUM(CASE WHEN result IS NOT NULL AND result != '' THEN 1 ELSE 0 END) as success_count,
               AVG(duration_ms) as avg_duration_ms
        FROM agent_actions
        GROUP BY task_name
        ORDER BY call_count DESC;
    """)
    return [
        {
            "tool_name": row[0],
            "call_count": row[1],
            "success_count": row[2],
            "avg_duration_ms": round(row[3], 1) if row[3] else None,
        }
        for row in cursor.fetchall()
    ]


def get_cached_tools(cursor: sqlite3.Cursor) -> list[dict]:
    """Tool cache entries — shows which tools had caching."""
    cursor.execute("""
        SELECT tool_name, COUNT(*) as cache_entries,
               MIN(fetched_at) as first_cached,
               MAX(fetched_at) as last_cached
        FROM tool_cache
        GROUP BY tool_name
        ORDER BY cache_entries DESC;
    """)
    return [
        {
            "tool_name": row[0],
            "cache_entries": row[1],
            "first_cached": row[2],
            "last_cached": row[3],
        }
        for row in cursor.fetchall()
    ]


def get_provider_cost_history(cursor: sqlite3.Cursor) -> list[dict]:
    """Provider cost history from model_usage — spend per provider per day."""
    cursor.execute("""
        SELECT provider, model_id,
               SUM(cost_usd) as total_cost,
               SUM(tokens_in) as total_tokens_in,
               SUM(tokens_out) as total_tokens_out,
               COUNT(*) as call_count,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
               DATE(called_at) as date
        FROM model_usage
        GROUP BY provider, model_id, DATE(called_at)
        ORDER BY date DESC;
    """)
    return [
        {
            "provider": row[0],
            "model_id": row[1],
            "total_cost": row[2],
            "total_tokens_in": row[3],
            "total_tokens_out": row[4],
            "call_count": row[5],
            "success_count": row[6],
            "date": row[7],
        }
        for row in cursor.fetchall()
    ]


def get_provider_cost_summary(cursor: sqlite3.Cursor) -> list[dict]:
    """Aggregate cost summary per provider — total lifetime spend."""
    cursor.execute("""
        SELECT provider,
               SUM(cost_usd) as total_cost,
               SUM(tokens_in) as total_tokens_in,
               SUM(tokens_out) as total_tokens_out,
               COUNT(*) as total_calls,
               SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
               MIN(called_at) as first_call,
               MAX(called_at) as last_call
        FROM model_usage
        GROUP BY provider
        ORDER BY total_cost DESC;
    """)
    return [
        {
            "provider": row[0],
            "total_cost_usd": row[1],
            "total_tokens_in": row[2],
            "total_tokens_out": row[3],
            "total_calls": row[4],
            "success_count": row[5],
            "first_call": row[6],
            "last_call": row[7],
        }
        for row in cursor.fetchall()
    ]


def get_completed_tasks(cursor: sqlite3.Cursor) -> list[dict]:
    """Completed tasks from task_queue — for MEMORY.md seeding."""
    cursor.execute("""
        SELECT id, task_name, status, result, created_at, completed_at, duration_ms
        FROM task_queue
        WHERE status = 'completed' OR status = 'done'
        ORDER BY completed_at DESC
        LIMIT 50;
    """)
    return [
        {
            "task_id": row[0],
            "task_name": row[1],
            "status": row[2],
            "result": row[3][:200] if row[3] else None,
            "created_at": row[4],
            "completed_at": row[5],
            "duration_ms": row[6],
        }
        for row in cursor.fetchall()
    ]


def get_memory_entries(cursor: sqlite3.Cursor) -> list[dict]:
    """Curated memory entries — candidates for MEMORY.md seed."""
    cursor.execute("""
        SELECT id, key, content, layer, created, updated, active
        FROM memory
        WHERE active = 1
        ORDER BY updated DESC;
    """)
    return [
        {
            "id": row[0],
            "key": row[1],
            "content": row[2][:500] if row[2] else None,
            "layer": row[3],
            "created": row[4],
            "updated": row[5],
        }
        for row in cursor.fetchall()
    ]


def get_table_summary(cursor: sqlite3.Cursor) -> list[dict]:
    """Summary of all tables and row counts."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cursor.fetchall()]
    summary = []
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM [{t}]")
        count = cursor.fetchone()[0]
        summary.append({"table": t, "rows": count})
    return summary


def build_migration_manifest(
    table_summary: list[dict],
    tools: list[dict],
    cached_tools: list[dict],
    cost_summary: list[dict],
    cost_daily: list[dict],
    completed_tasks: list[dict],
    memory_entries: list[dict],
) -> dict:
    """Build the migration manifest from audit data."""
    used_tools = [t for t in tools if t["call_count"] > 0]
    unused_tools = [t for t in tools if t["call_count"] == 0]

    return {
        "generated_at": datetime.now().isoformat(),
        "source": "PrivyBot",
        "target": "DuggerBot",
        "note": "Generated from stale Nitro 5 DB copy. Re-run against Tower for authoritative data.",
        "database_summary": table_summary,
        "tool_utilization": {
            "active_tools": [t["tool_name"] for t in used_tools],
            "unused_tools": [t["tool_name"] for t in unused_tools],
            "total_active": len(used_tools),
            "total_unused": len(unused_tools),
            "detail": used_tools,
        },
        "cached_tools": cached_tools,
        "provider_cost_summary": cost_summary,
        "provider_cost_daily": cost_daily[:30],
        "completed_tasks_sample": completed_tasks,
        "memory_entries_for_seed": memory_entries,
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
    print(f"  Database: {db_path}")
    print(f"  Size: {db_path.stat().st_size / 1024 / 1024:.1f} MB")

    table_summary = get_table_summary(cursor)
    print(f"  Tables: {len(table_summary)}")

    try:
        tools = get_tool_utilization(cursor)
        active = [t for t in tools if t["call_count"] > 0]
        print(f"  Agent actions: {len(tools)} unique tasks ({sum(t['call_count'] for t in tools)} total executions)")
        print(f"  Active tools: {len(active)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: agent_actions query failed: {e}", file=sys.stderr)
        tools = []

    try:
        cached_tools = get_cached_tools(cursor)
        print(f"  Cached tools: {len(cached_tools)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: tool_cache query failed: {e}", file=sys.stderr)
        cached_tools = []

    try:
        cost_summary = get_provider_cost_summary(cursor)
        total_spend = sum(c["total_cost_usd"] or 0 for c in cost_summary)
        print(f"  Provider cost summary: {len(cost_summary)} providers, ${total_spend:.4f} total")
        for c in cost_summary:
            print(f"    {c['provider']}: ${c['total_cost_usd']:.4f} ({c['total_calls']} calls)")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: model_usage summary query failed: {e}", file=sys.stderr)
        cost_summary = []

    try:
        cost_daily = get_provider_cost_history(cursor)
        print(f"  Daily cost records: {len(cost_daily)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: model_usage daily query failed: {e}", file=sys.stderr)
        cost_daily = []

    try:
        completed_tasks = get_completed_tasks(cursor)
        print(f"  Completed tasks (sample): {len(completed_tasks)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: task_queue query failed: {e}", file=sys.stderr)
        completed_tasks = []

    try:
        memory_entries = get_memory_entries(cursor)
        print(f"  Active memory entries: {len(memory_entries)}")
    except sqlite3.OperationalError as e:
        print(f"  WARNING: memory query failed: {e}", file=sys.stderr)
        memory_entries = []

    conn.close()

    manifest = build_migration_manifest(
        table_summary, tools, cached_tools,
        cost_summary, cost_daily,
        completed_tasks, memory_entries,
    )

    output_path = Path(args.output)
    output_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nMigration manifest written to: {output_path}")
    print(f"  Active tools: {manifest['tool_utilization']['total_active']}")
    print(f"  Unused tools: {manifest['tool_utilization']['total_unused']}")
    print(f"\nNOTE: This is stale Nitro 5 data. Re-run against Tower's live DB for authoritative manifest.")


if __name__ == "__main__":
    main()
