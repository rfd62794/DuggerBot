"""Twin protocol Pydantic schemas. Imports only TaskType and CallerIdentity from router."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from duggerbot.router.models import TaskType, CallerIdentity


class InstanceRole(str, Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"


class Nitro5State(str, Enum):
    UNKNOWN = "unknown"
    REGISTERED = "registered"
    ONLINE = "online"
    STALE = "stale"       # 3 missed heartbeats (90s)
    OFFLINE = "offline"   # 5 missed heartbeats (150s)


class InstanceCapabilities(BaseModel):
    ollama_model: str
    mcp_port: int
    providers: list[str]


class TwinRegistration(BaseModel):
    role: InstanceRole
    host: str
    mcp_port: int
    capabilities: InstanceCapabilities
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TwinHeartbeat(BaseModel):
    role: InstanceRole
    host: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str


class TwinStatus(BaseModel):
    state: Nitro5State
    role: InstanceRole | None = None
    host: str | None = None
    last_seen: datetime | None = None
    latency_ms: float | None = None


class DelegationRequest(BaseModel):
    task_id: str
    task_type: TaskType
    prompt: str
    from_role: InstanceRole
    timeout_seconds: float = 5.0


class DelegationResponse(BaseModel):
    task_id: str
    accepted: bool
    reason: str | None = None
    provider: str | None = None   # Which provider handled it, if accepted


class ProviderUsageRecord(BaseModel):
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class UsageSummary(BaseModel):
    date: str                                      # YYYY-MM-DD
    providers: dict[str, ProviderUsageRecord]      # provider_name → usage
