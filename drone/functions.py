from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable

import httpx

from drone.constants import (
    BASE_X,
    BASE_Y,
    BASE_Z,
    BATTERY_CHARGE_RATE,
    BATTERY_DRAIN_DELIVER,
    BATTERY_DRAIN_PER_CELL,
    BATTERY_DRAIN_SCAN,
    BATTERY_LOW_THRESHOLD,
    SCAN_RADIUS_DEFAULT,
)
from drone.core.config import SIM_SERVER_URL
from drone.models.drone import Drone, DroneStatus
from drone.models.results import (
    BatteryResult,
    DeliverResult,
    MoveResult,
    Position,
    ReturnResult,
    ScanArea,
    ScanResult,
    StatusResult,
    SurvivorSignal,
)
from drone.pathfinding import astar

logger = logging.getLogger(__name__)

# Buildings are generated 3–10 units tall. Above this threshold the drone
# flies over all buildings and A* treats every cell as passable.
MAX_BUILDING_HEIGHT: int = 10

# Maps internal DroneStatus → (MCP status string, current_task string | None)
# MCP contract uses: idle | busy | returning | charging | offline
# "busy" covers any active operation; current_task gives the detail.
_MCP_STATUS: dict[DroneStatus, tuple[str, str | None]] = {
    DroneStatus.IDLE:       ("idle",      None),
    DroneStatus.MOVING:     ("busy",      "moving"),
    DroneStatus.SCANNING:   ("busy",      "scanning"),
    DroneStatus.DELIVERING: ("busy",      "delivering"),
    DroneStatus.RETURNING:  ("returning", None),
    DroneStatus.CHARGING:   ("charging",  None),
}


async def _charge_loop(
    drone: Drone,
    on_tick: Callable[[Drone], Awaitable[None]] | None = None,
) -> None:
    """Gradually charge battery by BATTERY_CHARGE_RATE % per second until full.

    Runs as a background asyncio task started by return_to_base.
    Stops automatically when battery hits 100% or drone leaves CHARGING status
    (e.g. a new move command was issued before fully charged).

    on_tick is called after every charge increment so the router can push
    a live battery update to Map Engine — Map Engine sees the battery rising in real-time.
    """
    while drone.battery < 100.0 and drone.status == DroneStatus.CHARGING:
        await asyncio.sleep(1.0)
        drone.battery = min(100.0, round(drone.battery + BATTERY_CHARGE_RATE, 2))
        logger.debug("charging: %s battery=%.1f%%", drone.id, drone.battery)
        if on_tick:
            await on_tick(drone)
    logger.info("charging complete: %s battery=%.1f%%", drone.id, drone.battery)


def _manhattan(x1: int, y1: int, x2: int, y2: int) -> int:
    return abs(x1 - x2) + abs(y1 - y2)


def _drain(drone: Drone, amount: float) -> None:
    drone.battery = max(0.0, round(drone.battery - amount, 2))


async def move_to(
    drone: Drone,
    x: int,
    y: int,
    z: int = 0,
    on_waypoint: Callable[[Drone, int], Awaitable[None]] | None = None,
    moving_status: DroneStatus = DroneStatus.MOVING,
) -> MoveResult:
    """Move the drone to (x, y, z), navigating around obstacles.

    Fetches the current blocked-cell set from the Map Engine WS cache,
    then runs A* to find a path. Movement is step-by-step (one cell at a time):

    - Battery is drained per actual distance walked (not straight-line).
    - Azimuth is updated at each turn so the camera always faces forward.
    - A* is re-run before every step using the freshest blocked-cell cache,
      so the drone reacts to grid_update messages that arrive mid-path
      (new rubble, debris cleared, another drone entering a cell).
    - on_waypoint is awaited after each step so the router can push
      a WS position event to map engine for smooth map animation.

    Returns:
      "arrived" — reached (x, y, z) successfully.
      "blocked" — battery critical OR no passable path exists; drone stays put.
    """
    if drone.battery_critical:
        logger.warning("move_to refused — battery critical (%.1f%%)", drone.battery)
        return MoveResult(
            drone_id=drone.id,
            success=False,
            status="blocked",
            new_position=Position(**drone.position),
            battery_remaining_pct=drone.battery,
        )

    # Already at the target — no movement needed, just update z if different
    if drone.x == x and drone.y == y:
        drone.z = z
        drone.status = DroneStatus.IDLE
        return MoveResult(
            drone_id=drone.id,
            success=True,
            status="arrived",
            new_position=Position(x=x, y=y, z=z),
            battery_remaining_pct=drone.battery,
        )

    # Import here to avoid a top-level circular import (map_client imports drone models)
    from drone.core.map_client import map_client

    goal = (x, y)
    steps = 0
    start_z = drone.z
    start_x, start_y = drone.x, drone.y
    total_h_dist = _manhattan(drone.x, drone.y, x, y)

    while (drone.x, drone.y) != goal:
        if drone.battery_critical:
            logger.warning("move_to aborted mid-path — battery critical (%.1f%%)", drone.battery)
            return MoveResult(
                drone_id=drone.id,
                success=False,
                status="blocked",
                new_position=Position(**drone.position),
                battery_remaining_pct=drone.battery,
            )

        # Ask A*: "what is the shortest path from here to goal, avoiding blocked cells?"
        # We call this before EVERY single step — not just once at the start.
        # Because the Map Engine pushes grid_update messages in real-time,
        # _blocked may have changed since the last step (new rubble, other drone moved).
        # Re-planning every step means the drone automatically reroutes mid-path.
        # Above max building height -> fly straight over everything

        blocked = set() if drone.z > MAX_BUILDING_HEIGHT else map_client.get_blocked()

        path = astar((drone.x, drone.y), goal, blocked)

        if not path:
            # A* returned empty — goal is completely surrounded, no way through.
            # Return "blocked" so the LLM knows to re-plan at a higher level.
            logger.warning(
                "move_to: no path from (%d,%d) to (%d,%d) — blocked",
                drone.x, drone.y, x, y,
            )
            return MoveResult(
                drone_id=drone.id,
                success=False,
                status="blocked",
                new_position=Position(**drone.position),
                battery_remaining_pct=drone.battery,
            )

        # Take only the FIRST step of the path, then re-plan next iteration.
        # Never commit to the full path upfront — always recheck before each cell.
        wx, wy = path[0]
        step_dist = _manhattan(drone.x, drone.y, wx, wy)
        _drain(drone, step_dist * BATTERY_DRAIN_PER_CELL)

        # Update azimuth to face the direction of travel
        dx, dy = wx - drone.x, wy - drone.y
        if dx != 0 or dy != 0:
            drone.azimuth = math.degrees(math.atan2(dx, -dy)) % 360

        drone.x, drone.y = wx, wy

        # Gradually interpolate z toward target based on horizontal progress

        if total_h_dist > 0:

            h_traveled = _manhattan(start_x, start_y, drone.x, drone.y)

            progress = min(h_traveled / total_h_dist, 1.0)

            drone.z = round(start_z + (z - start_z) * progress)

        else:

            drone.z = z
        drone.status = moving_status  # MOVING by default, DELIVERING/RETURNING when called by those functions
        steps += 1

        # Push per-step position update so map shows the drone moving
        # cell-by-cell. step_dist drives eta_ms for smooth animation lerp.
        if on_waypoint:
            await on_waypoint(drone, step_dist)

    drone.status = DroneStatus.IDLE
    logger.info(
        "move_to: %s arrived at (%d, %d, %d) in %d step(s), battery=%.1f%%",
        drone.id, x, y, z, steps, drone.battery,
    )
    return MoveResult(
        drone_id=drone.id,
        success=True,
        status="arrived",
        new_position=Position(x=x, y=y, z=z),
        battery_remaining_pct=drone.battery,
    )


async def passive_waypoint_scan(drone: Drone, radius: int = 3) -> None:
    """Lightweight thermal sweep fired at each movement waypoint.

    Only runs for scanner drones (thermal_scan capability required).
    Uses the drone's current azimuth and FOV so only what's in the forward
    cone is detected — matching the visual FOV cone in the UI.

    Called fire-and-forget from on_waypoint — never awaited, so it does not
    add latency to the movement loop. Results go into map_client's heat buffer;
    thermal_scan merges them on the next explicit commanded scan.
    """
    if not drone.has_capability("thermal_scan"):
        return  # delivery drones have no thermal camera

    from drone.core.map_client import map_client
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SIM_SERVER_URL}/scan",
                params={
                    "x": drone.x,
                    "y": drone.y,
                    "z": drone.z,
                    "radius": radius,
                    "azimuth": drone.azimuth,
                    "fov": drone.fov,
                },
                timeout=3.0,
            )
        readings = resp.json()
        if readings:
            map_client.add_heat_readings(readings)
            logger.debug("passive_waypoint_scan: buffered %d reading(s) at (%d,%d)", len(readings), drone.x, drone.y)
    except Exception:
        pass  # silent — passive scan failure must never disrupt movement


async def thermal_scan(drone: Drone, radius: int = SCAN_RADIUS_DEFAULT) -> ScanResult:
    scan_pos = Position(x=drone.x, y=drone.y, z=drone.z)

    if not drone.has_capability("thermal_scan"):
        logger.warning("thermal_scan refused — drone %s (type=%s) lacks capability", drone.id, drone.type)
        return ScanResult(
            drone_id=drone.id,
            scan_position=scan_pos,
            survivors_detected=False,
            detections=[],
            scan_area=ScanArea(cx=drone.x, cy=drone.y, r=radius),
            battery_remaining_pct=drone.battery,
        )

    if drone.battery_critical:
        logger.warning("thermal_scan refused — battery critical (%.1f%%)", drone.battery)
        return ScanResult(
            drone_id=drone.id,
            scan_position=scan_pos,
            survivors_detected=False,
            detections=[],
            scan_area=ScanArea(cx=drone.x, cy=drone.y, r=radius),
            battery_remaining_pct=drone.battery,
        )

    drone.status = DroneStatus.SCANNING
    _drain(drone, BATTERY_DRAIN_SCAN)

    # Active scan — query sim server for thermal readings at current position.
    # Passive buffer — heat_signature readings pushed by the sim server's background
    # scanner while the drone was flying past (no explicit scan needed).
    # Merge both: same grid cell keeps the highest temperature reading seen.
    from drone.core.map_client import map_client

    all_temps: dict[tuple[int, int], float] = {}

    # Rotation sweep: drone rotates 360 degrees in steps equal to its FOV.
    # At each angle the camera scans what is in its forward cone, then the drone
    # rotates to the next angle. Full circle = num_steps * fov_per_step >= 360.
    # send_position at each step so the UI shows the drone physically spinning.
    num_steps = math.ceil(360 / drone.fov)
    step_angle = 360 / num_steps
    original_azimuth = drone.azimuth

    for i in range(num_steps):
        drone.azimuth = (i * step_angle) % 360
        await map_client.send_position(drone, 0)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{SIM_SERVER_URL}/scan",
                    params={
                        "x": drone.x,
                        "y": drone.y,
                        "z": drone.z,
                        "radius": radius,
                        "azimuth": drone.azimuth,
                        "fov": drone.fov,
                    },
                    timeout=5.0,
                )
            for r in resp.json():
                key = (int(round(r["x"])), int(round(r["y"])))
                all_temps[key] = max(all_temps.get(key, 0.0), r.get("temp_celsius", 0.0))
        except Exception:
            logger.exception("thermal_scan: step %d scan failed", i)
        await asyncio.sleep(0.1)

    drone.azimuth = original_azimuth
    await map_client.send_position(drone, 0)  # restore facing direction in UI

    # Merge passive buffer (keeps whichever temp is higher per cell)
    for r in map_client.get_recent_heat():
        key = (int(round(r["x"])), int(round(r["y"])))
        all_temps[key] = max(all_temps.get(key, 0.0), r.get("temp_celsius", 0.0))

    # All raw readings for heatmap rendering (every cell, any temperature)
    raw_readings: list[dict] = [
        {"x": x, "y": y, "temp_celsius": round(temp, 1)}
        for (x, y), temp in all_temps.items()
    ]

    # Detections = only the human-range readings (30–42°C)
    detections: list[SurvivorSignal] = [
        SurvivorSignal(
            x=x,
            y=y,
            confidence=round(min(temp / 37.5, 1.0), 3),
        )
        for (x, y), temp in all_temps.items()
        if 30 < temp < 42  # human range: >42°C = fire/equipment, ignored
    ]

    drone.status = DroneStatus.IDLE

    logger.info(
        "thermal_scan: %s scanned r=%d from (%d, %d), found %d signal(s)",
        drone.id, radius, drone.x, drone.y, len(detections),
    )
    return ScanResult(
        drone_id=drone.id,
        scan_position=scan_pos,
        survivors_detected=len(detections) > 0,
        detections=detections,
        raw_readings=raw_readings,
        scan_area=ScanArea(cx=drone.x, cy=drone.y, r=radius),
        battery_remaining_pct=drone.battery,
    )


async def deliver_aid(
    drone: Drone,
    x: int,
    y: int,
    z: int = 0,
    on_waypoint: Callable[[Drone, int], Awaitable[None]] | None = None,
) -> DeliverResult:
    if not drone.has_capability("delivery_aid"):
        logger.warning("deliver_aid refused — drone %s (type=%s) lacks capability", drone.id, drone.type)
        return DeliverResult(
            drone_id=drone.id,
            success=False,
            status="failed",
            delivered_to=Position(**drone.position),
            battery_remaining_pct=drone.battery,
            message=f"Drone type '{drone.type.value}' does not support aid delivery.",
        )

    if drone.battery_critical:
        logger.warning("deliver_aid refused — battery critical (%.1f%%)", drone.battery)
        return DeliverResult(
            drone_id=drone.id,
            success=False,
            status="failed",
            delivered_to=Position(**drone.position),
            battery_remaining_pct=drone.battery,
            message="Battery critical — cannot deliver aid.",
        )

    drone.status = DroneStatus.DELIVERING

    # Navigate to target using A* (same obstacle avoidance as move_to).
    # moving_status=DELIVERING keeps the drone status as "delivering" the whole
    # approach — not "moving" — so MCP and Map Engine see the correct operation.
    move_result = await move_to(drone, x, y, z, on_waypoint=on_waypoint, moving_status=DroneStatus.DELIVERING)

    if not move_result.success:
        # Couldn't reach the target — blocked by obstacles or battery died mid-path
        return DeliverResult(
            drone_id=drone.id,
            success=False,
            status="failed",
            delivered_to=Position(**drone.position),
            battery_remaining_pct=drone.battery,
            message="Could not reach delivery target — path blocked or battery critical.",
        )

    # Arrived — drop the aid package
    _drain(drone, BATTERY_DRAIN_DELIVER)
    drone.status = DroneStatus.IDLE

    logger.info("deliver_aid: %s delivered at (%d, %d, %d), battery=%.1f%%", drone.id, x, y, z, drone.battery)
    return DeliverResult(
        drone_id=drone.id,
        success=True,
        status="delivered",
        delivered_to=Position(x=x, y=y, z=z),
        battery_remaining_pct=drone.battery,
        message="Aid delivered successfully.",
    )


async def get_battery_status(drone: Drone) -> BatteryResult:
    return BatteryResult(
        drone_id=drone.id,
        battery_pct=drone.battery,
        charging=drone.is_charging,
        is_low=drone.battery_low,
        low_threshold_pct=BATTERY_LOW_THRESHOLD,
    )


async def get_drone_status(drone: Drone) -> StatusResult:
    mcp_status, current_task = _MCP_STATUS.get(drone.status, ("idle", None))
    return StatusResult(
        drone_id=drone.id,
        status=mcp_status,
        current_task=current_task,
        position=Position(**drone.position),
        battery=drone.battery,
    )


async def return_to_base(
    drone: Drone,
    on_waypoint: Callable[[Drone, int], Awaitable[None]] | None = None,
    on_tick: Callable[[Drone], Awaitable[None]] | None = None,
) -> ReturnResult:
    if drone.status == DroneStatus.CHARGING:
        return ReturnResult(
            drone_id=drone.id,
            success=True,
            status="arrived",
            position=Position(**drone.position),
            battery_pct=drone.battery,
            message="Already at base and charging.",
            eta_seconds=0,
        )

    # Manhattan distance to base computed upfront — used as eta estimate (Option A).
    # Actual A* path may be longer if obstacles force a detour, but "eta" implies
    # it is an estimate so this is acceptable and standard practice.
    eta = _manhattan(drone.x, drone.y, BASE_X, BASE_Y)

    # Navigate home using A* — avoids obstacles same as move_to/deliver_aid.
    # RETURNING status is used so Map Engine shows the correct state during the trip home.
    move_result = await move_to(
        drone, BASE_X, BASE_Y, BASE_Z,
        on_waypoint=on_waypoint,
        moving_status=DroneStatus.RETURNING,
    )

    if not move_result.success:
        logger.warning("return_to_base: %s could not reach base — path blocked", drone.id)
        return ReturnResult(
            drone_id=drone.id,
            success=False,
            status="blocked",
            position=Position(**drone.position),
            battery_pct=drone.battery,
            message="Could not reach base — path blocked or battery critical.",
            eta_seconds=0,
        )

    # Arrived at base — start gradual charge.
    # Cancel any existing charge task first (prevents duplicate tasks if called twice).
    if drone._charge_task and not drone._charge_task.done():
        drone._charge_task.cancel()
    drone.status = DroneStatus.CHARGING
    # on_tick is called every second so the router can push live battery
    # updates to Map Engine — Map Engine sees battery rising in real-time.
    drone._charge_task = asyncio.create_task(_charge_loop(drone, on_tick=on_tick))

    logger.info("return_to_base: %s at base, charging (%.1f%% → 100%%)", drone.id, drone.battery)
    return ReturnResult(
        drone_id=drone.id,
        success=True,
        status="arrived",
        position=Position(x=BASE_X, y=BASE_Y, z=BASE_Z),
        battery_pct=drone.battery,
        message=f"Drone at base. Charging at {BATTERY_CHARGE_RATE}%/s.",
        eta_seconds=eta,
    )