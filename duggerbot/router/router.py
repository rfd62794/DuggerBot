"""Accept a TaskRequest, apply routing rules, check health and budget, return a RouteResult."""

from pathlib import Path

import yaml

from duggerbot.router.models import (
    TaskRequest,
    TaskType,
    RouteResult,
    ProviderExhaustedError,
    BudgetExceededError,
)
from duggerbot.router.registry import ProviderRegistry
from duggerbot.router.health import HealthChecker
from duggerbot.router.ledger import UsageLedger


class ModelRouter:
    def __init__(
        self,
        registry: ProviderRegistry,
        health: HealthChecker,
        ledger: UsageLedger,
        routing_config: dict,
    ) -> None:
        self._registry = registry
        self._health = health
        self._ledger = ledger
        self._routing_config = routing_config

    async def route(self, request: TaskRequest) -> RouteResult:
        """
        Route a TaskRequest to the best available provider.

        Chain resolution:
        1. If require_local=True → use local_inference chain from routing.yaml
        2. Look up task_overrides for request.task_type
        3. Fall back to default_chain if no override
        4. Walk chain: check health, check budget (Claude only), return first viable
        5. If all exhausted → raise ProviderExhaustedError
        """
        chain = self._get_chain(request)
        tried: list[str] = []

        for provider_name in chain:
            provider = self._registry.get(provider_name)
            if provider is None or not provider.enabled:
                continue

            status = await self._health.check(provider)
            if not status.available:
                tried.append(provider_name)
                continue

            if provider.daily_cap_usd is not None:
                try:
                    await self._ledger.check_budget(
                        provider_name, provider.daily_cap_usd, estimated_cost=0.0
                    )
                except BudgetExceededError:
                    tried.append(provider_name)
                    continue

            budget_remaining = 0.0
            if provider.daily_cap_usd is not None:
                today_cost = await self._ledger.get_today_cost(provider_name)
                budget_remaining = provider.daily_cap_usd - today_cost

            return RouteResult(
                provider=provider_name,
                model=provider.models[0] if provider.models else "",
                task_type=request.task_type,
                fallback_chain=tried,
                budget_remaining_usd=budget_remaining,
            )

        raise ProviderExhaustedError(
            f"All providers exhausted for {request.task_type.value}. Tried: {tried}"
        )

    def _get_chain(self, request: TaskRequest) -> list[str]:
        """Return ordered provider names for this request."""
        routing = self._routing_config.get("routing", {})

        if request.require_local:
            overrides = routing.get("task_overrides", {})
            if "local_inference" in overrides:
                return overrides["local_inference"]

        task_key = request.task_type.value
        overrides = routing.get("task_overrides", {})
        if task_key in overrides:
            return overrides[task_key]

        return routing.get("default_chain", [])

    @classmethod
    def from_config(
        cls,
        providers_path: Path,
        routing_path: Path,
        health: HealthChecker,
        ledger: UsageLedger,
    ) -> "ModelRouter":
        """Convenience constructor — loads both config files."""
        registry = ProviderRegistry(providers_path)
        registry.load()

        with open(routing_path) as f:
            routing_config = yaml.safe_load(f)

        return cls(registry, health, ledger, routing_config)
