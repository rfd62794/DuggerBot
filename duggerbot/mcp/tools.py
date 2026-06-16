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
