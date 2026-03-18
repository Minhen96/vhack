from __future__ import annotations

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
    HYBRID = "hybrid"


CAPABILITIES: dict[DroneType, list[str]] = {
    DroneType.SCANNER: [
        "thermal_scan",
        "move_to",
        "return_to_base",
        "get_battery_status",
        "get_drone_status",
    ],
    DroneType.DELIVERY: [
        "deliver_aid",
        "move_to",
        "return_to_base",
        "get_battery_status",
        "get_drone_status",
    ],
    DroneType.HYBRID: [
        "thermal_scan",
        "deliver_aid",
        "move_to",
        "return_to_base",
        "get_battery_status",
        "get_drone_status",
    ],
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
    # azimuth:     horizontal facing direction in degrees (0 = east, 90 = north)
    #              updated automatically on every move_to call
    # elevation:   vertical camera tilt in degrees (-90 = straight down, 0 = horizon)
    #              drones point their camera downward by default
    # scan_radius: how many grid cells the drone can sense — used by Ken to draw FOV cone
    # fov:         camera lens angle in degrees — configurable via DRONE_FOV in constants.py
    azimuth: float = 0.0
    elevation: float = -90.0
    scan_radius: int = SCAN_RADIUS_DEFAULT
    fov: float = DRONE_FOV

    capabilities: list[str] = field(init=False)

    def __post_init__(self) -> None:
        self.capabilities = CAPABILITIES[self.type]

    @property
    def position(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "z": self.z}

    @property
    def spherical(self) -> dict[str, float]:
        """Camera orientation + FOV for Ken's 3D map renderer."""
        return {
            "azimuth": self.azimuth,
            "elevation": self.elevation,
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
        A hybrid can do both.
        """
        return name in self.capabilities
