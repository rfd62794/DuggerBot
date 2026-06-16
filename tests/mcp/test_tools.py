"""Tests for duggerbot.mcp.tools — Phase 2."""

from duggerbot.mcp.tools import get_tool_list


def _tool_by_name(name: str):
    return next(t for t in get_tool_list() if t.name == name)


def test_tool_list_has_five_tools():
    """get_tool_list() returns list of length 5."""
    assert len(get_tool_list()) == 5


def test_all_tools_have_name():
    """Every tool has a non-empty string name."""
    for tool in get_tool_list():
        assert isinstance(tool.name, str)
        assert len(tool.name) > 0


def test_all_tools_have_description():
    """Every tool has a non-empty description."""
    for tool in get_tool_list():
        assert isinstance(tool.description, str)
        assert len(tool.description) > 0


def test_research_requires_query():
    """research inputSchema has 'query' in required."""
    tool = _tool_by_name("research")
    assert "query" in tool.inputSchema.get("required", [])


def test_fast_lookup_requires_query():
    """fast_lookup inputSchema has 'query' in required."""
    tool = _tool_by_name("fast_lookup")
    assert "query" in tool.inputSchema.get("required", [])


def test_local_inference_requires_prompt():
    """local_inference inputSchema has 'prompt' in required."""
    tool = _tool_by_name("local_inference")
    assert "prompt" in tool.inputSchema.get("required", [])


def test_get_provider_status_no_required_params():
    """get_provider_status required is empty or absent."""
    tool = _tool_by_name("get_provider_status")
    required = tool.inputSchema.get("required", [])
    assert len(required) == 0


def test_get_cost_today_no_required_params():
    """get_cost_today required is empty or absent."""
    tool = _tool_by_name("get_cost_today")
    required = tool.inputSchema.get("required", [])
    assert len(required) == 0
