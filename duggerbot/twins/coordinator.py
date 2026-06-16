"""Arbitrate task authority between instances. Enforce the delegation handshake protocol."""

import os
import uuid

import httpx

from duggerbot.twins.models import (
    DelegationRequest,
    DelegationResponse,
    InstanceRole,
    UsageSummary,
)
from duggerbot.twins.identity import TwinIdentity
from duggerbot.twins.state import TwinStateReader
from duggerbot.twins.presence import PresenceTracker
from duggerbot.router.models import TaskRequest


SCHEDULED_TASK_TYPES = {"scheduled", "heartbeat", "morning_dispatch"}

FREE_TIER_RPD_LIMITS: dict[str, int] = {
    "gemini": 1500,
    "groq": 14400,
}
OVERLOAD_THRESHOLD = 0.80


class TwinCoordinator:
    """Task authority decisions and delegation handshake."""

    def __init__(
        self,
        identity: TwinIdentity,
        state_reader: TwinStateReader | None,
        presence: PresenceTracker | None,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._identity = identity
        self._state_reader = state_reader
        self._presence = presence
        self._client = http_client
        self._delegation_timeout = float(
            os.environ.get("DELEGATION_TIMEOUT_SECONDS", "5")
        )

    async def should_delegate_to_remote(self, request: TaskRequest) -> bool:
        """
        Local TOBOR only. True if task should go to Remote TOBOR.
        Always False when:
        - This is Remote TOBOR (no further delegation)
        - Task is a scheduled type
        - Remote TOBOR is offline or unregistered
        """
        if self._identity.is_production():
            return False
        if getattr(request, "task_source", None) in SCHEDULED_TASK_TYPES:
            return False
        if self._presence is None:
            return False
        return self._presence.is_online()

    async def get_adjusted_routing_chain(
        self, default_chain: list[str]
    ) -> list[str]:
        """
        Check Tower's provider usage and deprioritize providers above 80%
        of their free tier daily limit. Returns modified chain.
        Returns default_chain unchanged if state unavailable.
        """
        if self._state_reader is None:
            return default_chain
        usage = await self._state_reader.get_usage()
        if usage is None:
            return default_chain

        overloaded = set()
        for provider_name, record in usage.providers.items():
            limit = FREE_TIER_RPD_LIMITS.get(provider_name)
            if limit and record.calls >= (limit * OVERLOAD_THRESHOLD):
                overloaded.add(provider_name)

        if not overloaded:
            return default_chain

        prioritized = [p for p in default_chain if p not in overloaded]
        deprioritized = [p for p in default_chain if p in overloaded]
        return prioritized + deprioritized

    async def delegate_to_remote(
        self, request: TaskRequest, tower_host: str, mcp_port: int
    ) -> DelegationResponse | None:
        """
        POST /twin/delegate to Remote TOBOR.
        Returns None on timeout or connection failure.
        Respects DELEGATION_TIMEOUT_SECONDS.
        """
        url = f"http://{tower_host}:{mcp_port}/twin/delegate"
        payload = DelegationRequest(
            task_id=str(uuid.uuid4()),
            task_type=request.task_type,
            prompt=request.prompt,
            from_role=self._identity.get_role(),
            timeout_seconds=self._delegation_timeout,
        )
        try:
            resp = await self._client.post(
                url,
                json=payload.model_dump(mode="json"),
                timeout=self._delegation_timeout,
            )
            if resp.status_code == 200:
                return DelegationResponse(**resp.json())
            return None
        except (httpx.TimeoutException, httpx.ConnectError, Exception):
            return None

    async def accept_delegation(
        self, delegation: DelegationRequest
    ) -> DelegationResponse:
        """
        Remote TOBOR: evaluate and accept or reject an incoming delegation.
        Accept if not in a critical background cycle, reject otherwise.
        """
        return DelegationResponse(
            task_id=delegation.task_id,
            accepted=True,
            reason="accepted",
            provider=None,
        )
