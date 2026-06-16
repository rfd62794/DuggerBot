"""HTTP client that reads Tower's state endpoints. Never raises on network failure."""

import os

import httpx

from duggerbot.twins.models import UsageSummary


class TwinStateReader:
    """REST client for Tower state endpoints. Used by Local TOBOR (Nitro 5) only."""

    def __init__(
        self,
        tower_host: str,
        mcp_port: int,
        auth_token: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._base_url = f"http://{tower_host}:{mcp_port}"
        self._auth_token = auth_token
        self._client = http_client
        self._timeout = float(os.environ.get("STATE_REQUEST_TIMEOUT_SECONDS", "2"))

    async def get_usage(self) -> UsageSummary | None:
        """GET /twin/state/usage. Returns None on any failure."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/twin/state/usage",
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                return None
            return UsageSummary(**resp.json())
        except (httpx.TimeoutException, httpx.ConnectError, Exception):
            return None

    async def get_provider_statuses(self) -> dict | None:
        """GET /twin/state/providers. Returns None on any failure."""
        try:
            resp = await self._client.get(
                f"{self._base_url}/twin/state/providers",
                headers=self._auth_headers(),
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                return None
            return resp.json()
        except (httpx.TimeoutException, httpx.ConnectError, Exception):
            return None

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._auth_token}"}
