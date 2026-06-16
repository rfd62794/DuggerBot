"""Poll each provider's health endpoint and return current availability status."""

import asyncio
import time

import httpx

from duggerbot.router.models import Provider, ProviderStatus


class HealthChecker:
    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def check(self, provider: Provider) -> ProviderStatus:
        """Poll provider health endpoint. Never raises — returns status."""
        start = time.monotonic()
        try:
            response = await self._client.get(provider.health_endpoint, timeout=5.0)
            latency = (time.monotonic() - start) * 1000
            if response.status_code < 400:
                return ProviderStatus(
                    name=provider.name,
                    available=True,
                    latency_ms=round(latency, 1),
                )
            else:
                return ProviderStatus(
                    name=provider.name,
                    available=False,
                    latency_ms=round(latency, 1),
                    error=f"HTTP {response.status_code}",
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as e:
            latency = (time.monotonic() - start) * 1000
            return ProviderStatus(
                name=provider.name,
                available=False,
                latency_ms=round(latency, 1),
                error=str(e),
            )

    async def check_all(self, providers: list[Provider]) -> dict[str, ProviderStatus]:
        """Check all providers. Returns dict[provider_name → ProviderStatus]."""
        results = await asyncio.gather(*(self.check(p) for p in providers))
        return {status.name: status for status in results}
