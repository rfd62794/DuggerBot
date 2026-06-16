"""Tower-side state machine tracking Nitro 5's presence. In-memory only."""

from datetime import datetime, timezone, timedelta

from duggerbot.twins.models import (
    TwinRegistration,
    TwinHeartbeat,
    TwinStatus,
    Nitro5State,
    InstanceRole,
)


HEARTBEAT_INTERVAL_SECONDS = 30
STALE_THRESHOLD = 3    # missed heartbeats → STALE
OFFLINE_THRESHOLD = 5  # missed heartbeats → OFFLINE


class PresenceTracker:
    """Tower-side tracker for Nitro 5 presence. In-memory only."""

    def __init__(self) -> None:
        self._registration: TwinRegistration | None = None
        self._last_heartbeat: datetime | None = None
        self._state: Nitro5State = Nitro5State.UNKNOWN

    def register(self, registration: TwinRegistration) -> None:
        """Accept Nitro 5 registration. Sets state to REGISTERED."""
        self._registration = registration
        self._state = Nitro5State.REGISTERED

    def record_heartbeat(self, heartbeat: TwinHeartbeat) -> None:
        """Update last_heartbeat timestamp. Sets state to ONLINE."""
        self._last_heartbeat = datetime.now(timezone.utc)
        self._state = Nitro5State.ONLINE

    def get_status(self) -> TwinStatus:
        """Compute current state based on time since last heartbeat."""
        if self._state == Nitro5State.UNKNOWN:
            return TwinStatus(state=Nitro5State.UNKNOWN)

        if self._last_heartbeat is not None:
            elapsed = (datetime.now(timezone.utc) - self._last_heartbeat).total_seconds()
            missed_beats = elapsed / HEARTBEAT_INTERVAL_SECONDS

            if missed_beats >= OFFLINE_THRESHOLD:
                self._state = Nitro5State.OFFLINE
            elif missed_beats >= STALE_THRESHOLD:
                self._state = Nitro5State.STALE
            # else: keep current state (ONLINE or REGISTERED)

        role = self._registration.role if self._registration else None
        host = self._registration.host if self._registration else None

        return TwinStatus(
            state=self._state,
            role=role,
            host=host,
            last_seen=self._last_heartbeat,
        )

    def is_online(self) -> bool:
        """True only when state is ONLINE."""
        self.get_status()  # refresh state
        return self._state == Nitro5State.ONLINE
