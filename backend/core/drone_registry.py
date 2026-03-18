import math

from backend.models.drone import DroneCapability, DroneState, DroneStatus

BATTERY_LOW_THRESHOLD = 20.0
BASE_POSITION = (0, 0, 0)


class DroneRegistry:
    """In-memory store for drone fleet state."""

    def __init__(self) -> None:
        self._drones: dict[str, DroneState] = {}
        self._seed_fleet()

    def _seed_fleet(self) -> None:
        """Initialise 3 drones for simulation."""
        fleet = [
            DroneState(
                drone_id="drone-1",
                x=5,
                y=5,
                z=10,
                battery_pct=80.0,
                status=DroneStatus.IDLE,
                capabilities=[DroneCapability.THERMAL_SCAN, DroneCapability.DELIVERY_AID],
            ),
            DroneState(
                drone_id="drone-2",
                x=15,
                y=10,
                z=10,
                battery_pct=95.0,
                status=DroneStatus.IDLE,
                capabilities=[DroneCapability.THERMAL_SCAN, DroneCapability.DELIVERY_AID],
            ),
            DroneState(
                drone_id="drone-3",
                x=20,
                y=20,
                z=10,
                battery_pct=70.0,
                status=DroneStatus.IDLE,
                capabilities=[DroneCapability.THERMAL_SCAN, DroneCapability.DELIVERY_AID],
            ),
        ]
        for drone in fleet:
            self._drones[drone.drone_id] = drone

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def get_all(self) -> list[DroneState]:
        return list(self._drones.values())

    def get(self, drone_id: str) -> DroneState | None:
        return self._drones.get(drone_id)

    def update(self, drone: DroneState) -> None:
        self._drones[drone.drone_id] = drone

    # ------------------------------------------------------------------
    # Battery helpers
    # ------------------------------------------------------------------

    def is_battery_low(self, drone_id: str) -> bool:
        drone = self.get(drone_id)
        return drone is not None and drone.battery_pct < BATTERY_LOW_THRESHOLD

    def find_nearest_idle(
        self, from_x: int, from_y: int, from_z: int, exclude_id: str
    ) -> DroneState | None:
        """Return the closest idle drone, excluding the requesting drone."""
        candidates = [
            d
            for d in self._drones.values()
            if d.status == DroneStatus.IDLE and d.drone_id != exclude_id
        ]
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda d: math.sqrt(
                (d.x - from_x) ** 2 + (d.y - from_y) ** 2 + (d.z - from_z) ** 2
            ),
        )


# Singleton registry shared across the MCP server
registry = DroneRegistry()
