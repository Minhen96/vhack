"""
Drone registration endpoints
=============================
Drones call these endpoints on startup/shutdown to join or leave the fleet.

POST /register    — drone announces itself to the MCP server
POST /deregister  — drone removes itself from the active fleet
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.drone_registry import registry
from backend.events import push as push_event
from backend.models.drone import DroneCapability, DroneState, DroneStatus

router = APIRouter(tags=["drone-registry", "map"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    drone_id: str
    type: str
    capabilities: list[str]
    host: str
    port: int


class DeregisterRequest(BaseModel):
    drone_id: str


# ---------------------------------------------------------------------------
# GET /api/map/drones
# ---------------------------------------------------------------------------


@router.get("/api/map/drones")
def get_map_drones() -> list[dict]:
    """
    Return all active (non-offline) drones for the map display.

    Same data as the MCP list_active_drones tool — intended for the
    frontend map engine to poll and render current drone positions.
    """
    return [
        {
            "drone_id": d.drone_id,
            "x": d.x,
            "y": d.y,
            "z": d.z,
            "battery_pct": d.battery_pct,
            "status": d.status.value,
        }
        for d in registry.get_all()
        if d.status != DroneStatus.OFFLINE
    ]


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------


@router.post("/register")
async def register_drone(req: RegisterRequest) -> dict:
    """
    Register a drone with the MCP server.

    Called by a drone process on startup so the Command Agent can discover it
    via list_active_drones().  If the drone_id is already registered its
    entry is refreshed.
    """
    # Map capability strings to DroneCapability enum values; skip unknowns
    capability_map = {c.value: c for c in DroneCapability}
    parsed_capabilities = [
        capability_map[cap] for cap in req.capabilities if cap in capability_map
    ]

    existing = registry.get(req.drone_id)
    if existing:
        # Refresh host/port and mark online; preserve position & battery
        existing.type = req.type
        existing.host = req.host
        existing.port = req.port
        existing.capabilities = parsed_capabilities
        existing.status = DroneStatus.IDLE
        existing.current_task = None
        registry.register(existing)
        return {
            "success": True,
            "drone_id": req.drone_id,
            "message": f"Drone '{req.drone_id}' re-registered successfully.",
        }

    drone = DroneState(
        drone_id=req.drone_id,
        x=0,
        y=0,
        z=0,
        battery_pct=100.0,
        status=DroneStatus.IDLE,
        capabilities=parsed_capabilities,
        type=req.type,
        host=req.host,
        port=req.port,
    )
    registry.register(drone)

    # Notify the LLM agent that a new drone has joined the fleet mid-mission
    await push_event({
        "type": "drone_joined",
        "drone_id": req.drone_id,
        "drone_type": req.type,
        "capabilities": req.capabilities,
    })

    return {
        "success": True,
        "drone_id": req.drone_id,
        "message": f"Drone '{req.drone_id}' registered successfully.",
    }


# ---------------------------------------------------------------------------
# POST /deregister
# ---------------------------------------------------------------------------


@router.post("/deregister")
async def deregister_drone(req: DeregisterRequest) -> dict:
    """
    Deregister a drone from the MCP server.

    Called by a drone process on shutdown so the Command Agent stops
    dispatching tasks to it.
    """
    removed = registry.deregister(req.drone_id)
    if not removed:
        return {
            "success": False,
            "drone_id": req.drone_id,
            "message": f"Drone '{req.drone_id}' was not registered.",
        }

    # Notify the LLM agent that this drone has left the fleet
    await push_event({
        "type": "drone_left",
        "drone_id": req.drone_id,
    })

    return {
        "success": True,
        "drone_id": req.drone_id,
        "message": f"Drone '{req.drone_id}' deregistered successfully.",
    }
