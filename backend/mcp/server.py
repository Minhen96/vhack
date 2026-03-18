"""
MCP Server — Rescue Drone Tools
================================
Exposes drone fleet operations as standardised MCP tools.
The LLM Command Agent discovers and calls these tools via the
Model Context Protocol.

Run standalone:
    python -m backend.mcp.server

Or mount into an existing ASGI app:
    app.mount("/mcp", mcp.streamable_http_app())
"""

import math
import random

from mcp.server.fastmcp import FastMCP

from backend.core.drone_registry import BATTERY_LOW_THRESHOLD, registry
from backend.models.drone import DroneCapability, DroneStatus

mcp = FastMCP(
    name="rescue-drone-mcp",
    instructions=(
        "You are the MCP interface for a rescue drone fleet operating in an earthquake disaster zone. "
        "Always call list_active_drones first to discover the fleet. "
        "Monitor battery levels — when a drone drops below 20%, call request_backup immediately. "
        "Prioritise thermal_scan for survivor detection and delivery_aid for confirmed survivors."
    ),
)


# ---------------------------------------------------------------------------
# 1. list_active_drones
# ---------------------------------------------------------------------------


@mcp.tool()
def list_active_drones() -> list[dict]:
    """
    Discover all currently active (non-offline) drones on the network.

    Returns each drone's position (x, y, z), battery percentage, and status.
    Always call this first — drone IDs must never be hard-coded.
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
# 2. get_drone_capabilities
# ---------------------------------------------------------------------------


@mcp.tool()
def get_drone_capabilities(drone_id: str) -> dict:
    """
    Return the capability list for a specific drone.

    Capabilities:
      - thermal_scan  : detect heat signatures of survivors under rubble
      - delivery_aid  : carry and drop supplies to a target location
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    capability_descriptions = {
        DroneCapability.THERMAL_SCAN: (
            "Detects infrared radiation to identify heat signatures of survivors buried under rubble."
        ),
        DroneCapability.DELIVERY_AID: (
            "Carries and drops medical supplies, food, or rescue equipment to target coordinates."
        ),
    }

    return {
        "drone_id": drone_id,
        "capabilities": [
            {"name": c.value, "description": capability_descriptions[c]}
            for c in drone.capabilities
        ],
    }


# ---------------------------------------------------------------------------
# 3. get_drone_status
# ---------------------------------------------------------------------------


@mcp.tool()
def get_drone_status(drone_id: str) -> dict:
    """
    Return the current operational status of a drone.

    Possible values: idle, busy, returning, charging, offline.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    return {
        "drone_id": drone_id,
        "status": drone.status.value,
        "current_task": drone.current_task,
    }


# ---------------------------------------------------------------------------
# 4. get_battery_status
# ---------------------------------------------------------------------------


@mcp.tool()
def get_battery_status(drone_id: str) -> dict:
    """
    Return the battery percentage for a specific drone.

    When battery_pct is below the low threshold (20%), the agent should
    immediately call request_backup to dispatch a replacement drone.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    return {
        "drone_id": drone_id,
        "battery_pct": round(drone.battery_pct, 1),
        "is_low": drone.battery_pct < BATTERY_LOW_THRESHOLD,
        "low_threshold_pct": BATTERY_LOW_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# 5. move_to
# ---------------------------------------------------------------------------


@mcp.tool()
def move_to(drone_id: str, x: int, y: int, z: int) -> dict:
    """
    Move a drone to the given coordinates (x, y, z).

    Battery cost is proportional to distance (0.5 % per unit).
    If battery drops below the low threshold after moving, the response
    includes a backup_drone_available field — call request_backup immediately.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}
    if drone.status == DroneStatus.OFFLINE:
        return {"error": f"Drone '{drone_id}' is offline and cannot move."}

    distance = math.sqrt((x - drone.x) ** 2 + (y - drone.y) ** 2 + (z - drone.z) ** 2)
    battery_cost = round(distance * 0.5, 2)

    drone.x = x
    drone.y = y
    drone.z = z
    drone.battery_pct = max(0.0, drone.battery_pct - battery_cost)
    drone.status = DroneStatus.BUSY
    drone.current_task = f"moved to ({x},{y},{z})"
    registry.update(drone)

    result: dict = {
        "drone_id": drone_id,
        "success": True,
        "new_position": {"x": x, "y": y, "z": z},
        "battery_remaining_pct": round(drone.battery_pct, 1),
    }

    if drone.battery_pct < BATTERY_LOW_THRESHOLD:
        backup = registry.find_nearest_idle(x, y, z, exclude_id=drone_id)
        result["battery_warning"] = (
            f"Battery critically low at {round(drone.battery_pct, 1)}%. "
            "Call request_backup now."
        )
        result["backup_drone_available"] = backup.drone_id if backup else None

    return result


# ---------------------------------------------------------------------------
# 6. thermal_scan
# ---------------------------------------------------------------------------


@mcp.tool()
def thermal_scan(drone_id: str) -> dict:
    """
    Perform an infrared thermal scan at the drone's current position.

    Detects heat signatures (survivors, body heat) by sensing surface
    temperature variations caused by infrared radiation.  Each detected
    signature includes coordinates, temperature, and a confidence score.

    Battery cost: 5 % per scan.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}
    if DroneCapability.THERMAL_SCAN not in drone.capabilities:
        return {"error": f"Drone '{drone_id}' does not support thermal scanning."}
    if drone.battery_pct < 5.0:
        return {"error": f"Drone '{drone_id}' has insufficient battery to scan."}

    drone.battery_pct = max(0.0, drone.battery_pct - 5.0)
    drone.status = DroneStatus.BUSY
    drone.current_task = "thermal_scan"
    registry.update(drone)

    # Simulate detections around the drone's current position
    num_detections = random.randint(0, 3)
    detections = []
    for i in range(num_detections):
        detections.append(
            {
                "signature_id": f"sig-{drone_id}-{i + 1}",
                "x": drone.x + random.randint(-5, 5),
                "y": drone.y + random.randint(-5, 5),
                "z": 0,
                "heat_celsius": round(random.uniform(34.0, 37.5), 1),
                "confidence": round(random.uniform(0.60, 0.99), 2),
                "likely_survivor": True,
            }
        )

    return {
        "drone_id": drone_id,
        "scan_position": {"x": drone.x, "y": drone.y, "z": drone.z},
        "survivors_detected": len(detections),
        "detections": detections,
        "battery_remaining_pct": round(drone.battery_pct, 1),
    }


# ---------------------------------------------------------------------------
# 7. return_to_base
# ---------------------------------------------------------------------------


@mcp.tool()
def return_to_base(drone_id: str) -> dict:
    """
    Command a drone to return to base (0, 0, 0) for charging.

    Use this when battery is critically low OR when a drone has completed
    its mission.  The drone is fully recharged upon arrival (simulation).
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    drone.x, drone.y, drone.z = 0, 0, 0
    drone.battery_pct = 100.0
    drone.status = DroneStatus.CHARGING
    drone.current_task = "charging at base"
    registry.update(drone)

    return {
        "drone_id": drone_id,
        "success": True,
        "position": {"x": 0, "y": 0, "z": 0},
        "battery_pct": 100.0,
        "status": DroneStatus.CHARGING.value,
        "message": f"Drone {drone_id} has returned to base and is charging.",
    }


# ---------------------------------------------------------------------------
# 8. delivery_aid
# ---------------------------------------------------------------------------


@mcp.tool()
def delivery_aid(drone_id: str, x: int, y: int, z: int) -> dict:
    """
    Dispatch a drone to deliver aid (medical supplies, food, rescue equipment)
    to the specified coordinates.

    The drone must have the delivery_aid capability and sufficient battery.
    Battery cost: 0.5 % per unit of distance + 5 % for deployment.

    If battery drops below threshold after delivery, a backup recommendation
    is included in the response.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}
    if DroneCapability.DELIVERY_AID not in drone.capabilities:
        return {"error": f"Drone '{drone_id}' does not support aid delivery."}
    if drone.battery_pct < BATTERY_LOW_THRESHOLD:
        return {
            "error": (
                f"Drone '{drone_id}' battery too low ({round(drone.battery_pct, 1)}%). "
                "Return to base before attempting delivery."
            )
        }

    distance = math.sqrt((x - drone.x) ** 2 + (y - drone.y) ** 2 + (z - drone.z) ** 2)
    battery_cost = round(distance * 0.5 + 5.0, 2)

    drone.x = x
    drone.y = y
    drone.z = z
    drone.battery_pct = max(0.0, drone.battery_pct - battery_cost)
    drone.status = DroneStatus.BUSY
    drone.current_task = f"delivering aid to ({x},{y},{z})"
    registry.update(drone)

    result: dict = {
        "drone_id": drone_id,
        "success": True,
        "delivered_to": {"x": x, "y": y, "z": z},
        "battery_remaining_pct": round(drone.battery_pct, 1),
        "message": f"Aid successfully delivered to ({x},{y},{z}).",
    }

    if drone.battery_pct < BATTERY_LOW_THRESHOLD:
        backup = registry.find_nearest_idle(x, y, z, exclude_id=drone_id)
        result["battery_warning"] = (
            f"Battery critically low at {round(drone.battery_pct, 1)}%. "
            "Call request_backup now."
        )
        result["backup_drone_available"] = backup.drone_id if backup else None

    return result


# ---------------------------------------------------------------------------
# 9. request_backup  (battery-low rescue handoff)
# ---------------------------------------------------------------------------


@mcp.tool()
def request_backup(drone_id: str) -> dict:
    """
    Call this when a drone's battery drops below 20%.

    Finds the nearest idle drone, dispatches it to the low-battery drone's
    current position to take over the mission, and marks the original drone
    as returning to base.

    The agent should then call return_to_base on the original drone.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    backup = registry.find_nearest_idle(drone.x, drone.y, drone.z, exclude_id=drone_id)
    if not backup:
        return {
            "drone_id": drone_id,
            "success": False,
            "message": "No idle drones available for backup. Consider returning to base.",
        }

    # Dispatch backup drone
    backup.status = DroneStatus.BUSY
    backup.current_task = (
        f"backup for {drone_id} — heading to ({drone.x},{drone.y},{drone.z})"
    )
    registry.update(backup)

    # Mark original drone as returning
    drone.status = DroneStatus.RETURNING
    drone.current_task = "returning to base (low battery)"
    registry.update(drone)

    return {
        "drone_id": drone_id,
        "success": True,
        "backup_drone_id": backup.drone_id,
        "backup_dispatched_to": {"x": drone.x, "y": drone.y, "z": drone.z},
        "message": (
            f"Drone {backup.drone_id} dispatched to ({drone.x},{drone.y},{drone.z}) "
            f"to take over from {drone_id}. "
            f"Now call return_to_base('{drone_id}') to send it home."
        ),
    }


# ---------------------------------------------------------------------------
# Entry point — run as standalone MCP server (stdio transport)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
