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

import os

import httpx
from mcp.server.fastmcp import FastMCP

from backend.core.drone_registry import registry

mcp = FastMCP(
    name="rescue-drone-mcp",
    instructions=(
        "You are the MCP interface for a rescue drone fleet operating in an earthquake disaster zone. "
        "Call get_map_info and list_active_drones first. "
        "Use start_search (not move_to + thermal_scan) to begin an autonomous sweep — it returns immediately. "
        "Then loop on wait_for_event: act on survivor_found with delivery_aid, on battery_low with return_to_base, "
        "and exit the loop when all drones have sent search_complete."
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
            timeout=120.0,
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
            timeout=60.0,
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
    Skips delivery if the survivor at (x, y) is already aided (AID_SENT).
    If battery is below 30%, the drone charges first before delivering.
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    # Skip delivery if the target survivor is already aided (green on the map).
    # Survivor coords: X = backend x, Z = backend y (ground plane).
    sim_url = os.getenv("SIM_SERVER_URL", "http://localhost:8080")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{sim_url}/survivors", timeout=3.0)
            for s in resp.json():
                if s.get("status") in ("AID_SENT", "RESCUED"):
                    if abs(s.get("x", 0) - x) <= 2 and abs(s.get("z", 0) - y) <= 2:
                        return {
                            "skipped": True,
                            "message": f"Survivor at ({x}, {y}) already has status '{s['status']}'. Skipping delivery.",
                        }
        except Exception:
            pass  # if sim server unreachable, proceed anyway

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/drones/{drone_id}/deliver",
            json={"x": x, "y": y, "z": z},
            timeout=600.0,  # may include charge time (up to ~14s) + transit
        )
    return resp.json()


# ---------------------------------------------------------------------------
# 9. get_map_info  (discover map boundaries from sim server)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_map_info() -> dict:
    """
    Query the simulation server for the real map boundaries and base position.

    Returns x_min, x_max, y_min, y_max — use these as bounds for search_area
    calls instead of hard-coded values. Always call this before planning sectors.
    """
    sim_url = os.getenv("SIM_SERVER_URL", "http://localhost:8080")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{sim_url}/map-info", timeout=3.0)
            return resp.json()
        except Exception as e:
            return {"x_min": -40, "x_max": 40, "y_min": -40, "y_max": 40, "error": str(e)}


# ---------------------------------------------------------------------------
# 10. plan_search_zones  (automatic non-overlapping zone calculator)
# ---------------------------------------------------------------------------


@mcp.tool()
async def plan_search_zones(drone_ids: list[str]) -> list[dict]:
    """
    Pre-calculate non-overlapping search zones for a list of scanner drones.

    Queries the sim server for map bounds, then divides the map into equal
    vertical strips along the X axis — one per drone. Because the base is at
    the top edge (y_max), every drone starts at the base and immediately flies
    in a different X direction with zero overlap on the initial transit.

    Always call this at the start of Phase 2, and again when a drone_joined
    event fires (pass ALL current scanner drone IDs including the new arrival).

    Returns a list of zone dicts: [{drone_id, x1, y1, x2, y2}, ...]
    Pass each zone's coordinates directly to start_search.
    """
    n = len(drone_ids)
    if n == 0:
        return []

    sim_url = os.getenv("SIM_SERVER_URL", "http://localhost:8080")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{sim_url}/map-info", timeout=3.0)
            info = resp.json()
        except Exception:
            info = {"x_min": -40, "x_max": 40, "y_min": -40, "y_max": 40}

    x_min, x_max = info["x_min"], info["x_max"]
    y_min, y_max = info["y_min"], info["y_max"]
    base_x = info.get("base_x", 0)  # base is at the top edge, center x
    strip = (x_max - x_min) // n

    # Split map into X-axis strips. Sort by distance to base_x so the strip
    # containing the base (center) is assigned first — that drone starts
    # scanning immediately while others make a short transit left or right.
    raw_zones = []
    for i in range(n):
        x1 = x_min + i * strip
        x2 = x_min + (i + 1) * strip - 1 if i < n - 1 else x_max
        mid = (x1 + x2) / 2
        dist_to_base = abs(mid - base_x)
        raw_zones.append((dist_to_base, x1, x2))

    raw_zones.sort(key=lambda t: t[0])  # strip nearest to base_x first

    # Use y_max - 1 so the snake-pattern's range() excludes the base row (y_max).
    # The base sits at y_max, and searching right on the base edge looks like
    # "outside the map". The drone's transit from base to the first real waypoint
    # passively scans the base row, so no survivors there are missed.
    zones = []
    for drone_id, (_, x1, x2) in zip(drone_ids, raw_zones):
        zones.append({"drone_id": drone_id, "x1": x1, "y1": y_min, "x2": x2, "y2": y_max - 1})

    return zones


# ---------------------------------------------------------------------------
# 11. start_search  (fire-and-forget autonomous sweep)
# ---------------------------------------------------------------------------


@mcp.tool()
async def start_search(
    drone_id: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    z: int = 15,
    step: int = 10,
) -> dict:
    """
    Start an autonomous snake-pattern sweep in the background. Returns immediately.

    The drone begins sweeping its assigned sector with no LLM involvement between steps.
    Events are pushed automatically as they occur — call wait_for_event to receive them:
      survivor_found  → x, y, confidence
      battery_low     → drone_id, battery (call return_to_base immediately)
      search_complete → waypoints_visited, survivors_found, aborted

    Args:
        x1, y1 : one corner of the search area
        x2, y2 : opposite corner of the search area
        z      : flight altitude during search (default 15, clears all buildings)
        step   : grid spacing between scan points (default 10)
    """
    drone = registry.get(drone_id)
    if not drone:
        return {"error": f"Drone '{drone_id}' not found."}

    url = f"http://{drone.host}:{drone.port}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{url}/drones/{drone_id}/start_search",
            json={"x1": x1, "y1": y1, "x2": x2, "y2": y2, "z": z, "step": step},
            timeout=5.0,
        )
    return resp.json()


# ---------------------------------------------------------------------------
# 11. wait_for_event  (event-driven notification)
# ---------------------------------------------------------------------------


@mcp.tool()
async def wait_for_event(timeout: int = 30) -> dict:
    """
    Block until a drone event fires, then return it immediately.

    Never poll list_active_drones — use this instead. Call in a loop after
    start_search until all drones have sent a search_complete event.

    Event types returned:
      survivor_found  : {event, drone_id, x, y, confidence}
                        → call delivery_aid(drone_id, x, y, z=0) immediately
      battery_low     : {event, drone_id, battery}
                        → call return_to_base(drone_id) immediately
      search_complete : {event, drone_id, waypoints_visited, survivors_found, aborted}
                        → record completion; when ALL drones complete, mission done
      timeout         : {event: "timeout"}
                        → nothing happened; call wait_for_event again to keep waiting
    """
    from backend.events import wait

    event = await wait(float(timeout))
    if event is None:
        return {"event": "timeout", "message": "No events in the last 30s — searches still running."}
    return {"event": event["type"], **event}


# ---------------------------------------------------------------------------
# 12. request_backup  (battery-low rescue handoff)
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
