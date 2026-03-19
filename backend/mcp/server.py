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

import httpx
from mcp.server.fastmcp import FastMCP

from backend.core.drone_registry import registry

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
async def list_active_drones() -> list[dict]:
    """
    Discover all currently active drones on the network.

    Calls each registered drone's /status endpoint and returns live state.
    Always call this first — drone IDs must never be hard-coded.
    """
    results = []
    async with httpx.AsyncClient() as client:
        for d in registry.get_all():
            if not d.host:
                continue
            url = f"http://{d.host}:{d.port}"
            try:
                resp = await client.get(f"{url}/drones/{d.drone_id}/status", timeout=3.0)
                results.append(resp.json())
            except Exception:
                pass
    return results


# ---------------------------------------------------------------------------
# 2. get_drone_capabilities
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_drone_capabilities(drone_id: str) -> dict:
    """
    Return the capability list for a specific drone.

    Capabilities:
      - thermal_scan  : detect heat signatures of survivors under rubble
      - delivery_aid  : carry and drop supplies to a target location
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    return {"drone_id": drone_id, "capabilities": [c.value for c in drone.capabilities]}


# ---------------------------------------------------------------------------
# 3. get_drone_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_drone_status(drone_id: str) -> dict:
    """
    Return the current operational status of a drone.

    Includes position and battery — useful context for the agent.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{url}/drones/{drone_id}/status", timeout=3.0)
    return resp.json()


# ---------------------------------------------------------------------------
# 4. get_battery_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_battery_status(drone_id: str) -> dict:
    """
    Return the battery percentage for a specific drone.

    When battery is below 20%, call request_backup immediately.
    Battery charges gradually at 5%/s — poll this to track charging progress.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{url}/drones/{drone_id}/battery", timeout=3.0)
    return resp.json()


# ---------------------------------------------------------------------------
# 5. move_to
# ---------------------------------------------------------------------------


@mcp.tool()
async def move_to(drone_id: str, x: int, y: int, z: int) -> dict:
    """
    Move a drone to the given coordinates (x, y, z).

    Returns the new position and remaining battery.
    If status is 'blocked', A* found no path or battery is critical —
    call request_backup immediately.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/drones/{drone_id}/move",
            json={"x": x, "y": y, "z": z},
            timeout=10.0,
        )
    return resp.json()


# ---------------------------------------------------------------------------
# 6. thermal_scan
# ---------------------------------------------------------------------------


@mcp.tool()
async def thermal_scan(drone_id: str, radius: int = 8) -> dict:
    """
    Perform an infrared thermal scan at the drone's current position.

    Detects heat signatures (survivors) within the given radius (default 8).
    Battery cost: 5 % per scan.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/drones/{drone_id}/scan",
            json={"radius": radius},
            timeout=10.0,
        )
    return resp.json()


# ---------------------------------------------------------------------------
# 7. return_to_base
# ---------------------------------------------------------------------------


@mcp.tool()
async def return_to_base(drone_id: str) -> dict:
    """
    Command a drone to return to base for charging.

    Battery charges gradually at 5%/s — poll get_battery_status to track progress.
    Use this when battery is critically low OR when a drone has completed its mission.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{url}/drones/{drone_id}/return", timeout=10.0)
    return resp.json()


# ---------------------------------------------------------------------------
# 8. delivery_aid
# ---------------------------------------------------------------------------


@mcp.tool()
async def delivery_aid(drone_id: str, x: int, y: int, z: int) -> dict:
    """
    Dispatch a drone to deliver aid (medical supplies, food, rescue equipment)
    to the specified coordinates.

    The drone must have the delivery_aid capability and sufficient battery.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/drones/{drone_id}/deliver",
            json={"x": x, "y": y, "z": z},
            timeout=10.0,
        )
    return resp.json()


# ---------------------------------------------------------------------------
# 9. request_backup  (battery-low rescue handoff)
# ---------------------------------------------------------------------------


@mcp.tool()
async def request_backup(drone_id: str) -> dict:
    """
    Call this when a drone's battery drops below 20%.

    Finds the nearest idle drone by live status, dispatches it to the original
    drone's position, and commands the original drone to return to base.
    """
    async with httpx.AsyncClient() as client:
        statuses: list[tuple[str, str, dict]] = []
        for d in registry.get_all():
            if not d.host:
                continue
            url = f"http://{d.host}:{d.port}"
            try:
                r = await client.get(f"{url}/drones/{d.drone_id}/status", timeout=3.0)
                statuses.append((d.drone_id, url, r.json()))
            except Exception:
                pass

        original = next((s for s in statuses if s[0] == drone_id), None)
        if not original:
            return {"error": f"Drone '{drone_id}' not found or unreachable."}

        ox = original[2]["position"]["x"]
        oy = original[2]["position"]["y"]

        idle = [s for s in statuses if s[0] != drone_id and s[2]["status"] == "idle"]
        if not idle:
            return {"success": False, "message": "No idle drones available."}

        backup = min(
            idle,
            key=lambda s: abs(s[2]["position"]["x"] - ox) + abs(s[2]["position"]["y"] - oy),
        )
        backup_id, backup_url = backup[0], backup[1]

        await client.post(
            f"{backup_url}/drones/{backup_id}/move",
            json={"x": ox, "y": oy, "z": 0},
            timeout=10.0,
        )
        await client.post(f"{original[1]}/drones/{drone_id}/return", timeout=10.0)

    return {
        "drone_id": drone_id,
        "success": True,
        "backup_drone_id": backup_id,
        "message": f"Drone {backup_id} dispatched. {drone_id} returning to base.",
    }


# ---------------------------------------------------------------------------
# Entry point — run as standalone MCP server (stdio transport)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
