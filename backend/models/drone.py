from enum import Enum
from pydantic import BaseModel


class DroneStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    RETURNING = "returning"
    CHARGING = "charging"
    OFFLINE = "offline"


class DroneCapability(str, Enum):
    THERMAL_SCAN = "thermal_scan"
    DELIVERY_AID = "delivery_aid"


class DroneState(BaseModel):
    drone_id: str
    x: int
    y: int
    z: int
    battery_pct: float  # 0.0 – 100.0
    status: DroneStatus
    capabilities: list[DroneCapability]
    current_task: str | None = None
    type: str | None = None        # drone type reported at registration
    host: str | None = None        # drone's own HTTP host
    port: int | None = None        # drone's own HTTP port
