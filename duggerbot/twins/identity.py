"""Know this instance's INSTANCE_ROLE and capabilities. Produce an identity profile."""

import os

from duggerbot.twins.models import (
    InstanceCapabilities,
    InstanceRole,
    TwinHeartbeat,
)


class TwinIdentity:
    """Pure config reader — reads env at init, never writes, never makes network calls."""

    def __init__(self) -> None:
        role_str = os.environ.get("INSTANCE_ROLE", "development")
        self._role = InstanceRole(role_str)
        self._ollama_model = os.environ.get("OLLAMA_MODEL", "phi3.5:3.8b")
        self._mcp_port = int(os.environ.get("MCP_PORT", "8001"))
        self._version = "0.1.0"

    def get_role(self) -> InstanceRole:
        """Return this instance's role."""
        return self._role

    def is_production(self) -> bool:
        """True if this instance is Tower (production)."""
        return self._role == InstanceRole.PRODUCTION

    def is_development(self) -> bool:
        """True if this instance is Nitro 5 (development)."""
        return self._role == InstanceRole.DEVELOPMENT

    def get_capabilities(self) -> InstanceCapabilities:
        """Return this instance's capability profile."""
        return InstanceCapabilities(
            ollama_model=self._ollama_model,
            mcp_port=self._mcp_port,
            providers=[],  # populated from registry at runtime
        )

    def get_heartbeat(self) -> TwinHeartbeat:
        """Return a heartbeat payload identifying this instance."""
        host = os.environ.get("TOWER_HOST", "127.0.0.1")
        return TwinHeartbeat(
            role=self._role,
            host=host,
            version=self._version,
        )
