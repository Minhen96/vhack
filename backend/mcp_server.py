"""
MCP Server — Rescue Swarm Drone Tool Registry
----------------------------------------------
Exposes all drone control and environment query tools via FastMCP.

Usage (standalone stdio — for agent subprocess):
    python -m backend.mcp_server

Usage (bound to a running Simulation — for in-process integration):
    from backend.mcp_server import bind_simulation
    bind_simulation(sim)
"""
from __future__ import annotations

import logging

from fastmcp import FastMCP

from backend.simulation import Simulation
from backend.utils.heatmap import update_on_detection

logger = logging.getLogger(__name__)

mcp = FastMCP("rescue-swarm")

# ── Simulation binding ────────────────────────────────────────────────────────
# The MCP server holds a lazy reference to the shared Simulation instance.
# Call bind_simulation() once during app startup before any tool is invoked.

_sim: Simulation | None = None


def bind_simulation(sim: Simulation) -> None:
    """Bind the shared Simulation instance to this MCP server."""
    global _sim  # noqa: PLW0603
    _sim = sim
    logger.info("MCP server bound to simulation.")


def _get_sim() -> Simulation:
    if _sim is None:
        raise RuntimeError(
            "Simulation not bound. Call bind_simulation(sim) before using MCP tools."
        )
    return _sim


# ── Discovery ─────────────────────────────────────────────────────────────────


@mcp.tool()
def list_active_drones() -> list[dict]:
    """Return all drones currently online with their role, battery, and position."""
    return _get_sim().query_drones()


@mcp.tool()
def get_drone_status(drone_id: str) -> dict:
    """Return the full status of a specific drone by ID."""
    try:
        return _get_sim().query_drone(drone_id)
    except KeyError as exc:
        return {"error": str(exc)}


# ── Movement ──────────────────────────────────────────────────────────────────


@mcp.tool()
def move_to(drone_id: str, x: int, y: int) -> dict:
    """
    Move a drone to the target grid cell.

    Returns the planned path length and estimated ticks to arrive.
    Fails if the cell is out of bounds, impassable, or unreachable.
    """
    return _get_sim().command_move_to(drone_id, x, y)


def assign_sector(drone_id: str, sector: str) -> dict:
    """
    Internal helper — NOT exposed as an MCP tool.
    Use move_to with specific coordinates from context instead.

    sector must be one of: NW, NE, SW, SE.
    The drone is sent to the centre of the chosen quadrant.
    """
    sim = _get_sim()
    grid_size = len(sim.grid)
    half = grid_size // 2
    quarter = grid_size // 4

    sector_centres: dict[str, tuple[int, int]] = {
        "NW": (quarter, quarter),
        "NE": (half + quarter, quarter),
        "SW": (quarter, half + quarter),
        "SE": (half + quarter, half + quarter),
    }

    sector_upper = sector.upper()
    if sector_upper not in sector_centres:
        return {
            "success": False,
            "error": f"Unknown sector '{sector}'. Must be one of: NW, NE, SW, SE.",
        }

    tx, ty = sector_centres[sector_upper]

    # If the sector centre is impassable (e.g. water in typhoon), spiral outward
    # to find the nearest passable cell so the command never silently fails.
    if not sim.grid[ty][tx].passable:
        found = False
        for radius in range(1, grid_size):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = tx + dx, ty + dy
                    if 0 <= nx < grid_size and 0 <= ny < grid_size and sim.grid[ny][nx].passable:
                        tx, ty = nx, ny
                        found = True
                        break
                if found:
                    break
            if found:
                break

    result = sim.command_move_to(drone_id, tx, ty)
    result["sector"] = sector_upper
    result["target_x"] = tx
    result["target_y"] = ty
    return result


# ── Sensing ───────────────────────────────────────────────────────────────────


@mcp.tool()
def thermal_scan(drone_id: str) -> dict:
    """
    Perform a thermal scan of all cells within the drone's scan radius.

    Drone descends to scanning altitude (15 units), applying a +0.15 confidence
    bonus. Returns a dict mapping 'x,y' keys to confidence scores.
    Cells with survivors produce high confidence (0.7–1.0); empty cells score ~0.
    """
    return _get_sim().command_thermal_scan(drone_id)


@mcp.tool()
def deep_scan(drone_id: str, x: int, y: int) -> dict:
    """
    Perform a focused, high-confidence scan on a single cell.

    Higher accuracy than thermal_scan. Costs 2 extra battery.
    Registers this drone as a confirmer if a survivor is found —
    required for swarm consensus before dispatching a medic.
    """
    return _get_sim().command_deep_scan(drone_id, x, y)


# ── Resource management ───────────────────────────────────────────────────────


@mcp.tool()
def get_battery_status(drone_id: str) -> dict:
    """Return the current battery percentage for a drone."""
    try:
        drone = _get_sim().query_drone(drone_id)
        return {"drone_id": drone_id, "battery": drone["battery"]}
    except KeyError as exc:
        return {"error": str(exc)}


@mcp.tool()
def return_to_base(drone_id: str) -> dict:
    """
    Recall a drone to the base station for charging.

    Returns estimated ticks to arrive. The drone sets altitude to
    RETURNING (20 units) during transit.
    """
    return _get_sim().command_return_to_base(drone_id)


@mcp.tool()
def deploy_relay(x: int, y: int) -> dict:
    """
    Station an idle RELAY drone at the given position to extend mesh range.

    Use this when a scout moves beyond 8 cells from base without a relay in range.
    Fails if no idle relay drone is available.
    """
    return _get_sim().command_deploy_relay(x, y)


# ── Rescue ────────────────────────────────────────────────────────────────────


@mcp.tool()
def dispatch_medic(drone_id: str, target_x: int, target_y: int) -> dict:
    """
    Send a MEDIC drone to a confirmed survivor location.

    Only works for drones with role MEDIC. Altitude transitions to
    DELIVERING (5 units) en route. Ensure at least 2 scouts have confirmed
    the cell via deep_scan before calling this.
    """
    return _get_sim().command_dispatch_medic(drone_id, target_x, target_y)


@mcp.tool()
def deliver_aid(drone_id: str) -> dict:
    """
    Execute aid delivery at the drone's current position.

    Requires:
      - Drone altitude ≤ 8 (DELIVERING state, altitude 5).
      - Drone must carry a payload (MEDKIT or FOOD).
      - A survivor must be present at the drone's current cell.

    Returns an error dict if any condition is unmet.
    """
    return _get_sim().command_deliver_aid(drone_id)


# ── Environment ───────────────────────────────────────────────────────────────


@mcp.tool()
def get_map_state() -> dict:
    """
    Return a full grid snapshot including terrain, fire, debris, and survivor data.

    Use sparingly — prefer get_heatmap() for high-frequency queries.
    """
    return _get_sim().query_map_state()


@mcp.tool()
def get_heatmap() -> list[list[float]]:
    """
    Return the 2D survivor probability array (values 0.0–1.0).

    Indexed as [y][x]. Use this to identify high-priority search zones
    without fetching the full grid state.
    """
    return _get_sim().query_heatmap()


@mcp.tool()
def get_mission_status() -> dict:
    """
    Return current mission state.

    Includes: phase, tick, coverage %, survivors found/rescued/total,
    mesh health %, and isolated drone IDs.
    Call this at the start of every reasoning cycle.
    """
    return _get_sim().query_mission_status()


# ── Swarm coordination ────────────────────────────────────────────────────────


@mcp.tool()
def broadcast_finding(drone_id: str, x: int, y: int, confidence: float) -> dict:
    """
    Share a survivor detection with the swarm, boosting the heatmap at (x, y).

    Call this immediately after thermal_scan detects a survivor signal so other
    drones can converge on the area.
    """
    sim = _get_sim()
    rows = len(sim.grid)
    cols = len(sim.grid[0]) if rows else 0

    if not (0 <= x < cols and 0 <= y < rows):
        return {"success": False, "error": "Coordinates out of bounds."}

    clamped_confidence = max(0.0, min(1.0, confidence))
    update_on_detection(sim.grid, x, y, clamped_confidence)

    logger.info(
        "broadcast_finding: %s reported signal at (%d, %d) conf=%.2f",
        drone_id, x, y, clamped_confidence,
    )
    return {
        "success": True,
        "drone_id": drone_id,
        "x": x,
        "y": y,
        "confidence": clamped_confidence,
    }


@mcp.tool()
def request_confirmation(x: int, y: int) -> dict:
    """
    Request a second scout drone to confirm a survivor detection at (x, y).

    Finds the nearest idle SCOUT not already assigned to this cell and sends it
    to perform a deep_scan. Required as part of swarm consensus before dispatching
    a medic (2 independent confirmations with confidence > 0.7 needed).
    """
    from backend.models.drone import DroneRole, DroneStatus  # avoid top-level circular import

    sim = _get_sim()
    rows = len(sim.grid)
    cols = len(sim.grid[0]) if rows else 0

    if not (0 <= x < cols and 0 <= y < rows):
        return {"success": False, "error": "Coordinates out of bounds."}

    candidates = [
        d for d in sim.drones.values()
        if d.role == DroneRole.SCOUT
        and d.status in (DroneStatus.IDLE, DroneStatus.SCANNING)
        and d.target != (x, y)
        # Exclude drones whose square scan area already covers the target cell
        # (scan covers cells where |dx| ≤ radius AND |dy| ≤ radius, not Manhattan)
        and not (abs(d.x - x) <= d.scan_radius and abs(d.y - y) <= d.scan_radius)
    ]

    if not candidates:
        return {"success": False, "error": "No available scout drone for confirmation."}

    nearest = min(candidates, key=lambda d: abs(d.x - x) + abs(d.y - y))
    move_result = sim.command_move_to(nearest.id, x, y)
    if not move_result["success"]:
        return move_result

    return {
        "success": True,
        "assigned_drone": nearest.id,
        "target_x": x,
        "target_y": y,
        "eta_ticks": move_result["eta_ticks"],
    }


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run as a stdio MCP server for use with langchain-mcp-adapters or MCP Inspector.
    mcp.run()
