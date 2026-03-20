from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum

from drone.constants import BASE_X, BASE_Y, BASE_Z, DRONE_FOV, SCAN_RADIUS_DEFAULT


class DroneStatus(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    SCANNING = "scanning"
    DELIVERING = "delivering"
    RETURNING = "returning"
    CHARGING = "charging"


class DroneType(str, Enum):
    SCANNER = "scanner"
    DELIVERY = "delivery"


# Available on every drone regardless of type
COMMON_CAPABILITIES: list[str] = [
    "move_to",
    "return_to_base",
    "get_battery_status",
    "get_drone_status",
]

# Type-specific capabilities — what makes each type unique
CAPABILITIES: dict[DroneType, list[str]] = {
    DroneType.SCANNER:  ["thermal_scan"],
    DroneType.DELIVERY: ["delivery_aid"],
}


@dataclass
class Drone:
    id: str
    type: DroneType
    x: int = BASE_X
    y: int = BASE_Y
    z: int = BASE_Z
    battery: float = 100.0
    status: DroneStatus = DroneStatus.IDLE
    base_x: int = BASE_X
    base_y: int = BASE_Y
    base_z: int = BASE_Z

    # ── Camera orientation (spherical coordinates) ────────────────────────────
    # azimuth:     horizontal facing direction in degrees (0 = north, 90 = east, compass CW)
    #              updated automatically on every move_to call
    # elevation:   vertical camera tilt in degrees (-90 = straight down, 0 = horizon)
    #              drones point their camera downward by default
    # scan_radius: how many grid cells the drone can sense — used by map engine to draw FOV cone
    # fov:         camera lens angle in degrees — configurable via DRONE_FOV in constants.py
    azimuth: float = 0.0
    elevation: float = -45.0
    roll: float = 0.0
    scan_radius: int = SCAN_RADIUS_DEFAULT
    fov: float = DRONE_FOV

    capabilities: list[str] = field(init=False)

    # Background task that gradually charges battery while at base.
    # Stored here so it can be cancelled (e.g. drone dispatched mid-charge)
    # and to prevent duplicate charge tasks if return_to_base is called twice.
    _charge_task: asyncio.Task | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        # Full capability list = type-specific + common (sent to MCP and Map Engine on startup)
        self.capabilities = CAPABILITIES[self.type] + COMMON_CAPABILITIES

    @property
    def position(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @property
    def spherical(self) -> dict[str, float]:
        """Camera orientation + FOV for map engine."""
        return {
            "azimuth": self.azimuth,
            "elevation": self.elevation,
            "roll": self.roll,
            "scan_radius": self.scan_radius,
            "fov": self.fov,
        }

    @property
    def is_charging(self) -> bool:
        return self.status == DroneStatus.CHARGING

    @property
    def battery_low(self) -> bool:
        from drone.constants import BATTERY_LOW_THRESHOLD
        return self.battery <= BATTERY_LOW_THRESHOLD

    @property
    def battery_critical(self) -> bool:
        from drone.constants import BATTERY_CRITICAL_THRESHOLD
        return self.battery <= BATTERY_CRITICAL_THRESHOLD

    def has_capability(self, name: str) -> bool:
        """Return True if this drone supports the named capability.

        Capability is determined by drone type via the CAPABILITIES map.
        A scanner can thermal_scan but not deliver_aid.
        A delivery drone can deliver_aid but not thermal_scan.
        """
        return name in self.capabilities
