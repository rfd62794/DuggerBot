"""FastAPI APIRouter exposing all /twin/* endpoints. Zero business logic here."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from duggerbot.mcp.auth import verify_token
from duggerbot.router.models import CallerIdentity
from duggerbot.twins.identity import TwinIdentity
from duggerbot.twins.models import (
    DelegationRequest,
    DelegationResponse,
    TwinHeartbeat,
    TwinRegistration,
    TwinStatus,
    UsageSummary,
)

twin_router = APIRouter()


def _get_identity(request: Request) -> TwinIdentity:
    """Retrieve TwinIdentity from app state."""
    return request.app.state.twin_identity


async def _require_production(
    identity: TwinIdentity = Depends(_get_identity),
) -> TwinIdentity:
    """Dependency: reject with 403 if not production (Tower)."""
    if identity.is_development():
        raise HTTPException(status_code=403, detail="Tower only")
    return identity


@twin_router.get("/heartbeat")
async def heartbeat_get(request: Request):
    """Liveness check — no auth required. Explicit ADR-007 exception."""
    identity: TwinIdentity = request.app.state.twin_identity
    return {
        "status": "ok",
        "role": identity.get_role().value,
        "version": "0.1.0",
    }


@twin_router.post(
    "/register",
    dependencies=[Depends(verify_token), Depends(_require_production)],
)
async def register_post(registration: TwinRegistration, request: Request):
    """Nitro 5 registers its presence. Tower only."""
    presence = request.app.state.presence_tracker
    presence.register(registration)
    return {"status": "registered"}


@twin_router.post(
    "/heartbeat",
    dependencies=[Depends(verify_token), Depends(_require_production)],
)
async def heartbeat_post(heartbeat: TwinHeartbeat, request: Request):
    """Nitro 5 sends heartbeat. Tower only."""
    presence = request.app.state.presence_tracker
    presence.record_heartbeat(heartbeat)
    return {"status": "ok"}


@twin_router.get(
    "/nitro5/status",
    dependencies=[Depends(verify_token), Depends(_require_production)],
)
async def nitro5_status(request: Request):
    """Returns current Nitro 5 state. Tower only."""
    presence = request.app.state.presence_tracker
    status = presence.get_status()
    return status.model_dump()


@twin_router.get(
    "/state/usage",
    dependencies=[Depends(verify_token), Depends(_require_production)],
)
async def state_usage(request: Request):
    """Returns today's usage from UsageLedger. Tower only."""
    ledger = request.app.state.ledger
    summary = await ledger.get_daily_summary()
    return {
        "date": date.today().isoformat(),
        "providers": summary,
    }


@twin_router.get(
    "/state/providers",
    dependencies=[Depends(verify_token), Depends(_require_production)],
)
async def state_providers(request: Request):
    """Returns current provider health. Tower only."""
    health = request.app.state.health
    registry = request.app.state.registry
    providers = registry.list_enabled()
    statuses = await health.check_all(providers)
    return {
        name: {
            "available": s.available,
            "latency_ms": s.latency_ms,
            "error": s.error,
        }
        for name, s in statuses.items()
    }


@twin_router.post("/delegate", dependencies=[Depends(verify_token)])
async def delegate_post(delegation: DelegationRequest, request: Request):
    """Accept or reject a delegation request. Both instances."""
    coordinator = request.app.state.twin_coordinator
    response = await coordinator.accept_delegation(delegation)
    return response.model_dump()
