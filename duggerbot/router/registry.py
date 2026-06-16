"""Load providers.yaml and expose the provider list with their models and limits."""

from pathlib import Path

import yaml

from duggerbot.router.models import Provider, FreeTier


class ProviderRegistry:
    def __init__(self, config_path: Path) -> None:
        self._config_path = config_path
        self._providers: dict[str, Provider] = {}
        self._routing_order: list[str] = []

    def load(self) -> None:
        """Load providers.yaml. Raises FileNotFoundError if missing."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Provider config not found: {self._config_path}")

        with open(self._config_path) as f:
            raw = yaml.safe_load(f)

        providers_raw = raw.get("providers", {})
        for name, data in providers_raw.items():
            free_tier_data = data.get("free_tier")
            free_tier = FreeTier(**free_tier_data) if free_tier_data else None

            self._providers[name] = Provider(
                name=name,
                role=data["role"],
                models=data.get("models", []),
                free_tier=free_tier,
                cost_per_1k_tokens=data.get("cost_per_1k_tokens", 0.0),
                cost_per_1k_input_tokens=data.get("cost_per_1k_input_tokens"),
                cost_per_1k_output_tokens=data.get("cost_per_1k_output_tokens"),
                daily_cap_usd=data.get("daily_cap_usd"),
                enabled=data.get("enabled", True),
                health_endpoint=data["health_endpoint"],
                keep_alive=data.get("keep_alive"),
            )
            self._routing_order.append(name)

    def get(self, name: str) -> Provider | None:
        """Return Provider for name, or None if unknown."""
        return self._providers.get(name)

    def list_enabled(self) -> list[Provider]:
        """Return all enabled providers in file order."""
        return [p for p in self._providers.values() if p.enabled]

    def get_routing_order(self) -> list[str]:
        """Return ordered provider names as they appear in config."""
        return list(self._routing_order)
