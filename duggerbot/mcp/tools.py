"""Define the schema and signature for each MCP tool Claude can call."""

from mcp.types import Tool


def get_tool_list() -> list[Tool]:
    """Return all five MCP tool definitions. Pure data — no business logic."""
    return [
        Tool(
            name="research",
            description="Route a research query to the best available provider (Gemini primary).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The research query."},
                    "context_size": {
                        "type": "integer",
                        "description": "Approximate context window needed (tokens).",
                        "default": 0,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="fast_lookup",
            description="Route a fast lookup to the speed tier (Groq primary).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The lookup query."},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="local_inference",
            description="Run a prompt on the local model (Ollama). Private tasks only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "The prompt to run locally."},
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="get_provider_status",
            description="Return health and quota state for all providers.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_cost_today",
            description="Return Claude API spend today vs the $0.25 daily cap.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


def get_dev_tool_list() -> list[Tool]:
    """Return five developer tool definitions. Read-only, no provider calls."""
    return [
        Tool(
            name="verify_test_floor",
            description="Run pytest and return pass/fail/skip counts with floor_met bool.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="check_coverage",
            description="Run coverage and return per-module percentages with floor_met bool.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_project_state",
            description="Read docs/state/current.md and return structured phase state.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_open_issues",
            description="Read docs/issues/ and return list of open issues with severity.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_migration_manifest",
            description="Read migration_manifest.json and return tool utilization data.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="get_version",
            description="Returns version string, revision, git hash, instance role — no network.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="check_for_update",
            description="Fetches from origin, returns local vs remote revision comparison — slow.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="read_file",
            description="Read a file by absolute or repo-relative path. Returns file content as text.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path or path relative to repo root.",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="write_context",
            description="Write or overwrite a shared context entry. Claude writes directives, Devin reads them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Context key."},
                    "value": {"type": "string", "description": "Context value."},
                },
                "required": ["key", "value"],
            },
        ),
        Tool(
            name="read_context",
            description="Read a shared context entry by key. Returns value or null if not found.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Context key to read."},
                },
                "required": ["key"],
            },
        ),
        Tool(
            name="delete_context",
            description="Delete a shared context entry by key.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Context key to delete."},
                },
                "required": ["key"],
            },
        ),
        Tool(
            name="list_context",
            description="List all context keys, optionally filtered by prefix.",
            inputSchema={
                "type": "object",
                "properties": {
                    "prefix": {"type": "string", "description": "Optional key prefix filter.", "default": ""},
                },
            },
        ),
        Tool(
            name="dispatch_to_cline",
            description="Dispatch a bounded coding task to Cline CLI headless with a specified Ollama model.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The coding task to dispatch."},
                    "model": {"type": "string", "description": "Ollama model name (e.g. ollama/qwen3)."},
                },
                "required": ["task", "model"],
            },
        ),
        Tool(
            name="get_logs",
            description="Return last N lines of logs/duggerbot.log with encoding fallback.",
            inputSchema={
                "type": "object",
                "properties": {
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines to return from end of log (default: 50)",
                        "default": 50,
                    }
                },
                "required": [],
            },
        ),
    ]
