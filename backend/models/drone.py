from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.core.config import (
    ALTITUDE_CRUISING,
    ALTITUDE_TRANSITION_SPEED,
    BATTERY_DRAIN,
    COMM_RANGE,
    SCAN_RADIUS,
    SCAN_BASE_ACCURACY,
    ALTITUDE_SCANNING,
    ALTITUDE_DELIVERING,
    ALTITUDE_RETURNING,
)


class DroneRole(str, Enum):
    SCOUT = "SCOUT"
    MEDIC = "MEDIC"
    RELAY = "RELAY"
    HEAVY = "HEAVY"


class DroneStatus(str, Enum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    SCANNING = "SCANNING"
    DELIVERING = "DELIVERING"
    RETURNING = "RETURNING"
    CHARGING = "CHARGING"
    OFFLINE = "OFFLINE"


class AltitudeState(str, Enum):
    CRUISING = "CRUISING"
    SCANNING = "SCANNING"
    DELIVERING = "DELIVERING"
    RETURNING = "RETURNING"


# Target altitude value for each state
ALTITUDE_TARGET: dict[AltitudeState, int] = {
    AltitudeState.CRUISING: ALTITUDE_CRUISING,
    AltitudeState.SCANNING: ALTITUDE_SCANNING,
    AltitudeState.DELIVERING: ALTITUDE_DELIVERING,
    AltitudeState.RETURNING: ALTITUDE_RETURNING,
}


@dataclass
class Drone:
    id: str
    role: DroneRole
    x: int
    y: int

    # ── Battery ───────────────────────────────────────────────────────────────
    battery: float = 100.0

    # ── Status ────────────────────────────────────────────────────────────────
    status: DroneStatus = DroneStatus.IDLE

    # ── Payload ───────────────────────────────────────────────────────────────
    payload: str | None = None           # "MEDKIT" | "FOOD" | None

    # ── Communication ─────────────────────────────────────────────────────────
    communication_range: int = field(init=False)

    # ── Scanning ──────────────────────────────────────────────────────────────
    scan_radius: int = field(init=False)
    scan_accuracy: float = field(init=False)

    # ── Navigation ────────────────────────────────────────────────────────────
    path: list[tuple[int, int]] = field(default_factory=list)
    target: tuple[int, int] | None = None
    mission_id: str | None = None

    # ── Swarm ─────────────────────────────────────────────────────────────────
    leader: bool = False
    last_seen_tick: int = 0

    # ── Altitude (real simulation value) ──────────────────────────────────────
    altitude: int = ALTITUDE_CRUISING
    altitude_state: AltitudeState = AltitudeState.CRUISING

    def __post_init__(self) -> None:
        role_key = self.role.value
        self.communication_range = COMM_RANGE[role_key]
        self.scan_radius = SCAN_RADIUS[role_key]
        self.scan_accuracy = SCAN_BASE_ACCURACY[role_key]

    # ── Derived properties ────────────────────────────────────────────────────

    @property
    def battery_drain_rate(self) -> float:
        return BATTERY_DRAIN[self.role.value]

    @property
    def position(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def altitude_target(self) -> int:
        return ALTITUDE_TARGET[self.altitude_state]

    @property
    def at_target_altitude(self) -> bool:
        return self.altitude == self.altitude_target

    # ── State transitions ─────────────────────────────────────────────────────

    def set_altitude_state(self, state: AltitudeState) -> None:
        self.altitude_state = state

    def step_altitude(self) -> bool:
        """Move altitude one step toward target. Returns True if altitude changed."""
        target = self.altitude_target
        if self.altitude == target:
            return False
        step = ALTITUDE_TRANSITION_SPEED
        if self.altitude < target:
            self.altitude = min(self.altitude + step, target)
        else:
            self.altitude = max(self.altitude - step, target)
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role.value,
            "x": self.x,
            "y": self.y,
            "battery": round(self.battery, 1),
            "status": self.status.value,
            "payload": self.payload,
            "communication_range": self.communication_range,
            "scan_radius": self.scan_radius,
            "path": self.path,
            "target": list(self.target) if self.target else None,
            "mission_id": self.mission_id,
            "leader": self.leader,
            "altitude": self.altitude,
            "altitude_state": self.altitude_state.value,
        }
