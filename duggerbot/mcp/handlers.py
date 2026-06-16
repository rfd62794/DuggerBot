"""Execute tool calls by delegating to ModelRouter and returning structured results."""

import json

from mcp.types import TextContent

from duggerbot.router.models import (
    CallerIdentity,
    TaskRequest,
    TaskType,
    ProviderExhaustedError,
    BudgetExceededError,
)
from duggerbot.router.router import ModelRouter
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger
from duggerbot.router.registry import ProviderRegistry


async def handle_research(
    router: ModelRouter,
    arguments: dict,
    caller: CallerIdentity = CallerIdentity.CLAUDE,
) -> list[TextContent]:
    """Route research query. Returns RouteResult as TextContent.

    When caller is DEVIN: exclude 'claude' from provider chain.
    Never consume Claude API budget on Devin's behalf.
    """
    exclude = ["claude"] if caller == CallerIdentity.DEVIN else None
    request = TaskRequest(
        task_type=TaskType.RESEARCH,
        prompt=arguments.get("query", ""),
        context_size=arguments.get("context_size", 0),
    )
    try:
        result = await router.route(request)
        return [TextContent(
            type="text",
            text=json.dumps({
                "provider": result.provider,
                "model": result.model,
                "task_type": result.task_type.value,
                "fallback_chain": result.fallback_chain,
                "budget_remaining_usd": result.budget_remaining_usd,
            }),
        )]
    except ProviderExhaustedError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except BudgetExceededError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_fast_lookup(
    router: ModelRouter,
    arguments: dict,
    caller: CallerIdentity = CallerIdentity.CLAUDE,
) -> list[TextContent]:
    """Route fast lookup. Groq preferred per routing.yaml.

    When caller is DEVIN: exclude 'claude' from provider chain.
    """
    exclude = ["claude"] if caller == CallerIdentity.DEVIN else None
    request = TaskRequest(
        task_type=TaskType.FAST_LOOKUP,
        prompt=arguments.get("query", ""),
    )
    try:
        result = await router.route(request)
        return [TextContent(
            type="text",
            text=json.dumps({
                "provider": result.provider,
                "model": result.model,
                "task_type": result.task_type.value,
            }),
        )]
    except ProviderExhaustedError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except BudgetExceededError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_local_inference(
    router: ModelRouter,
    arguments: dict,
    caller: CallerIdentity = CallerIdentity.CLAUDE,
) -> list[TextContent]:
    """Route to Ollama. require_local=True on TaskRequest.

    When caller is DEVIN: exclude 'claude' from provider chain.
    """
    exclude = ["claude"] if caller == CallerIdentity.DEVIN else None
    request = TaskRequest(
        task_type=TaskType.LOCAL_INFERENCE,
        prompt=arguments.get("prompt", ""),
        require_local=True,
    )
    try:
        result = await router.route(request)
        return [TextContent(
            type="text",
            text=json.dumps({
                "provider": result.provider,
                "model": result.model,
                "task_type": result.task_type.value,
            }),
        )]
    except ProviderExhaustedError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except BudgetExceededError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def handle_get_provider_status(
    health: HealthChecker,
    registry: ProviderRegistry,
) -> list[TextContent]:
    """Check all providers. Return status dict as formatted TextContent."""
    providers = registry.list_enabled()
    statuses = await health.check_all(providers)
    result = {
        name: {
            "available": s.available,
            "latency_ms": s.latency_ms,
            "error": s.error,
        }
        for name, s in statuses.items()
    }
    return [TextContent(type="text", text=json.dumps(result))]


async def handle_get_cost_today(
    ledger: UsageLedger,
) -> list[TextContent]:
    """Return today's Claude API cost and remaining budget as TextContent."""
    today_cost = await ledger.get_today_cost("claude")
    cap = 0.25
    remaining = cap - today_cost
    summary = await ledger.get_daily_summary()
    return [TextContent(
        type="text",
        text=json.dumps({
            "claude_cost_today": round(today_cost, 4),
            "daily_cap_usd": cap,
            "remaining_usd": round(remaining, 4),
            "all_providers": summary,
        }),
    )]


TOOL_HANDLERS: dict[str, str] = {
    "research": "handle_research",
    "fast_lookup": "handle_fast_lookup",
    "local_inference": "handle_local_inference",
    "get_provider_status": "handle_get_provider_status",
    "get_cost_today": "handle_get_cost_today",
}
