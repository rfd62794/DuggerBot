"""Pydantic models: Provider, TaskType, TaskRequest, RouteResult, ProviderStatus."""

from enum import Enum
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class CallerIdentity(str, Enum):
    CLAUDE = "claude"
    DEVIN = "devin"


class TaskType(str, Enum):
    RESEARCH = "research"
    FAST_LOOKUP = "fast_lookup"
    LOCAL_INFERENCE = "local_inference"
    GENERAL = "general"


class FreeTier(BaseModel):
    rpd: int | None = None   # requests per day
    rpm: int | None = None   # requests per minute
    tpm: int | None = None   # tokens per minute


class Provider(BaseModel):
    name: str
    role: str                              # primary | speed | access | local | reserved
    models: list[str]
    free_tier: FreeTier | None = None
    cost_per_1k_tokens: float = 0.0
    cost_per_1k_input_tokens: float | None = None
    cost_per_1k_output_tokens: float | None = None
    daily_cap_usd: float | None = None    # Claude only
    enabled: bool = True
    health_endpoint: str
    keep_alive: int | None = None         # Ollama only


class ProviderStatus(BaseModel):
    name: str
    available: bool
    latency_ms: float | None = None
    error: str | None = None
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskRequest(BaseModel):
    task_type: TaskType
    prompt: str
    context_size: int = 0
    require_local: bool = False           # Force Ollama — private tasks only
    task_source: str | None = None        # scheduled, heartbeat, morning_dispatch, etc.


class RouteResult(BaseModel):
    provider: str
    model: str
    task_type: TaskType
    fallback_chain: list[str] = Field(default_factory=list)
    budget_remaining_usd: float = 0.0


class ProviderExhaustedError(Exception):
    """All providers in the routing chain are unavailable."""


class BudgetExceededError(Exception):
    """Claude API daily cap would be exceeded."""


class ProviderUnavailableError(Exception):
    """A specific provider is unavailable."""
