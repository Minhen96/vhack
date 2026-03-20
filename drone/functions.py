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
    BATTERY_CRITICAL_THRESHOLD,
    BATTERY_DRAIN_DELIVER,
    BATTERY_DRAIN_PER_CELL,
    BATTERY_DRAIN_SCAN,
    BATTERY_LOW_THRESHOLD,
    SCAN_RADIUS_DEFAULT,
)
from drone.core.config import MCP_URL, SIM_SERVER_URL
from drone.models.drone import Drone, DroneStatus
from drone.models.results import (
    BatteryResult,
    DeliverResult,
    MoveResult,
    Position,
    ReturnResult,
    ScanArea,
    ScanResult,
    SearchResult,
    StatusResult,
    SurvivorSignal,
)
from drone.pathfinding import astar

logger = logging.getLogger(__name__)

_BUCKET_SIZE = SCAN_RADIUS_DEFAULT  # must match backend/coverage.py BUCKET_SIZE
_MAX_ROLL_DEG = 22.5  # max bank angle in degrees (matches frontend PI/8)


async def _fetch_covered_buckets() -> set[tuple[int, int]]:
    """Query the backend for already-covered grid buckets (one call per search start)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{MCP_URL}/coverage", timeout=3.0)
            data = resp.json()
            return {(b[0], b[1]) for b in data.get("buckets", [])}
    except Exception:
        return set()


async def _report_covered(x: int, y: int) -> None:
    """Fire-and-forget: tell the backend this position has been scanned."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{MCP_URL}/internal/coverage",
                              json={"x": x, "y": y}, timeout=1.0)
    except Exception:
        pass


async def _push_event(event: dict) -> None:
    """Fire-and-forget: push an event to the backend event queue."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(f"{MCP_URL}/internal/event", json=event, timeout=2.0)
    except Exception:
        pass


def _bucket(x: int, y: int) -> tuple[int, int]:
    return (x // _BUCKET_SIZE, y // _BUCKET_SIZE)


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
    # Notify the LLM agent so it can restart the search immediately
    # instead of waiting for a wait_for_event(30) timeout to expire.
    asyncio.create_task(_push_event({"type": "charging_complete", "drone_id": drone.id}))


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

    info = await map_client.fetch_map_info()
    map_bounds = (info["x_min"], info["y_min"], info["x_max"], info["y_max"])

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

        blocked = set() if drone.z >= MAX_BUILDING_HEIGHT else map_client.get_blocked()

        path = astar((drone.x, drone.y), goal, blocked, bounds=map_bounds)

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

        # Update azimuth and roll to face the direction of travel
        dx, dy = wx - drone.x, wy - drone.y
        if dx != 0 or dy != 0:
            prev_az = drone.azimuth
            drone.azimuth = math.degrees(math.atan2(dx, -dy)) % 360
            az_diff = drone.azimuth - prev_az
            if az_diff > 180: az_diff -= 360
            if az_diff < -180: az_diff += 360
            target_roll = -math.copysign(_MAX_ROLL_DEG, az_diff) if abs(az_diff) > 0.01 else 0.0
        else:
            target_roll = 0.0
        drone.roll = round(drone.roll + (target_roll - drone.roll) * 0.3, 2)

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


async def passive_waypoint_scan(
    drone: Drone,
    radius: int = SCAN_RADIUS_DEFAULT,
    on_survivor: Callable[[int, int, float], Awaitable[None]] | None = None,
) -> None:
    """Lightweight thermal sweep fired at each movement waypoint.

    Only runs for scanner drones (thermal_scan capability required).
    Uses fov=360 (full-circle downward look) so the drone sees everything
    directly below it as it flies — not just the forward-facing 60° arc.

    Called fire-and-forget from on_waypoint — never awaited, so it does not
    add latency to the movement loop. Results go into map_client's heat buffer;
    thermal_scan merges them on the next explicit commanded scan.

    on_survivor(x, y, temp) is called for each human-range reading (30–42°C)
    so the background search task can push survivor_found events in real-time
    without waiting for the next explicit scan waypoint.
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
                    "elevation": drone.elevation,
                    "fov": drone.fov,
                },
                timeout=3.0,
            )
        readings = resp.json()
        if readings:
            map_client.add_heat_readings(readings)
            logger.debug("passive_waypoint_scan: buffered %d reading(s) at (%d,%d)", len(readings), drone.x, drone.y)
            if on_survivor:
                for r in readings:
                    temp = r.get("temp_celsius", 0.0)
                    if 30 < temp < 42:
                        await on_survivor(int(round(r["x"])), int(round(r["y"])), temp)
        # Mark every bucket along the ground projection of the camera cone:
        # from the drone's ground position to the footprint center.
        # At elevation=-45°, altitude z: footprint center is z units ahead; the
        # cone covers all buckets along that line, not just the far end.
        el_rad = math.radians(drone.elevation)
        az_rad = math.radians(drone.azimuth)
        if el_rad < 0 and drone.z > 0:
            h_dist = drone.z / math.tan(-el_rad)
            fpx = round(drone.x + h_dist * math.sin(az_rad))
            fpy = round(drone.y - h_dist * math.cos(az_rad))
        else:
            h_dist = 0.0
            fpx, fpy = drone.x, drone.y
        # Step along the line at BUCKET_SIZE intervals so every bucket is hit
        num_steps = max(1, round(h_dist / _BUCKET_SIZE))
        for i in range(num_steps + 1):
            t = i / num_steps
            cx = round(drone.x + (fpx - drone.x) * t)
            cy = round(drone.y + (fpy - drone.y) * t)
            asyncio.create_task(_report_covered(cx, cy))
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

    # Forward 180° sweep: passive_waypoint_scan already covered the rear hemisphere
    # (it fires fov=360 at every movement cell, so everything behind is scanned).
    # We only need the forward arc — centered on current heading, ±90° each side.
    # With FOV=60°: 3 steps × 60° = 180° total coverage.
    original_azimuth = drone.azimuth
    num_steps = math.ceil(360 / drone.fov)
    step_angle = drone.fov
    start_azimuth = original_azimuth - (num_steps - 1) / 2 * step_angle

    for i in range(num_steps):
        drone.azimuth = (start_azimuth + i * step_angle) % 360
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
                        "elevation": drone.elevation,
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


def _snake_waypoints(
    x1: int, y1: int, x2: int, y2: int, step: int,
    start_x: int = 0, start_y: int = 0,
) -> list[tuple[int, int]]:
    """Generate boustrophedon (snake) scan waypoints over a rectangular area.

    Starts from the corner nearest to (start_x, start_y) so the drone
    wastes minimum battery flying to the first waypoint.
    """
    lx, hx = min(x1, x2), max(x1, x2)
    ly, hy = min(y1, y2), max(y1, y2)
    xs = list(range(lx, hx + 1, step))
    ys = list(range(ly, hy + 1, step))

    # Pick the corner of this sector nearest to the drone's current position
    corners = [(lx, ly), (lx, hy), (hx, ly), (hx, hy)]
    near_cx, near_cy = min(corners, key=lambda c: abs(c[0] - start_x) + abs(c[1] - start_y))

    # Traverse y from the near edge toward the far edge
    if near_cy > (ly + hy) / 2:
        ys = list(reversed(ys))

    # First row starts from the x-edge nearest to the drone
    x_start_right = near_cx > (lx + hx) / 2

    waypoints: list[tuple[int, int]] = []
    for i, y in enumerate(ys):
        use_reversed = (i % 2 == 0) == x_start_right
        row = list(reversed(xs)) if use_reversed else xs
        for x in row:
            waypoints.append((x, y))
    return waypoints


async def search_area(
    drone: Drone,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    z: int = 15,
    step: int = 10,
    scan_radius: int = SCAN_RADIUS_DEFAULT,
    on_waypoint: Callable[[Drone, int], Awaitable[None]] | None = None,
    on_scan_complete: Callable[[Drone, ScanResult], Awaitable[None]] | None = None,
) -> SearchResult:
    """Autonomously sweep a rectangular area in a snake pattern, scanning at each waypoint.

    The drone moves and scans continuously — no LLM inference between each step.
    Battery is monitored: aborts immediately if battery drops below critical threshold.

    Returns aggregated detections and raw heatmap readings from the full sweep.
    """
    if not drone.has_capability("thermal_scan"):
        return SearchResult(
            drone_id=drone.id,
            waypoints_visited=0,
            waypoints_total=0,
            survivors_detected=False,
            detections=[],
            battery_remaining_pct=drone.battery,
            aborted=True,
            abort_reason=f"Drone type '{drone.type.value}' does not support thermal scanning.",
        )

    from drone.core.map_client import map_client
    info = await map_client.fetch_map_info()
    _base_x = int(info.get("base_x", BASE_X))
    _base_y = int(info.get("base_y", BASE_Y))

    all_waypoints = _snake_waypoints(x1, y1, x2, y2, step, start_x=drone.x, start_y=drone.y)
    # Query backend once for covered buckets — survives drone disconnect/reconnect
    covered_buckets = await _fetch_covered_buckets()
    waypoints = [(wx, wy) for wx, wy in all_waypoints if _bucket(wx, wy) not in covered_buckets]
    logger.info(
        "search_area: %s — %d/%d waypoints uncovered (skipping %d already scanned)",
        drone.id, len(waypoints), len(all_waypoints), len(all_waypoints) - len(waypoints),
    )
    all_temps: dict[tuple[int, int], float] = {}
    all_detections: dict[tuple[int, int], SurvivorSignal] = {}
    visited = 0

    for wx, wy in waypoints:
        if drone.battery_critical:
            logger.warning("search_area: aborting — battery critical (%.1f%%)", drone.battery)
            break

        # 1. Can we return from our CURRENT position?
        #    Check this first — if we can't make it home from here, abort immediately.
        current_return_cost = _manhattan(drone.x, drone.y, _base_x, _base_y) * BATTERY_DRAIN_PER_CELL
        if drone.battery - current_return_cost < BATTERY_CRITICAL_THRESHOLD:
            logger.warning(
                "search_area: aborting — cannot safely return from current position (%d,%d) "
                "(battery=%.1f%%, return_cost=%.1f%%)", drone.x, drone.y, drone.battery, current_return_cost,
            )
            break

        # 2. Can we reach the NEXT waypoint, scan, and still return from there?
        move_cost = _manhattan(drone.x, drone.y, wx, wy) * BATTERY_DRAIN_PER_CELL
        return_cost = _manhattan(wx, wy, _base_x, _base_y) * BATTERY_DRAIN_PER_CELL
        projected = drone.battery - move_cost - BATTERY_DRAIN_SCAN - return_cost
        if projected < BATTERY_CRITICAL_THRESHOLD:
            logger.warning(
                "search_area: aborting — not enough battery to reach (%d,%d) and return "
                "(projected %.1f%% < threshold %.1f%%)", wx, wy, projected, BATTERY_CRITICAL_THRESHOLD,
            )
            break

        # Move to waypoint — streams position updates via on_waypoint
        move_result = await move_to(drone, wx, wy, z, on_waypoint=on_waypoint)
        if not move_result.success:
            logger.warning("search_area: blocked at (%d,%d), skipping waypoint", wx, wy)
            continue

        if drone.battery_critical:
            break

        # Scan at this waypoint and report to backend coverage grid.
        # Mark the waypoint bucket and its 4 cardinal neighbours (±BUCKET_SIZE)
        # so waypoints spaced > BUCKET_SIZE apart don't leave uncovered gaps
        # between them (e.g. step=10, bucket=8 leaves x=-8..-1 unmarked).
        scan_result = await thermal_scan(drone, scan_radius)
        visited += 1
        for _dx, _dy in [(0, 0), (-_BUCKET_SIZE, 0), (_BUCKET_SIZE, 0), (0, -_BUCKET_SIZE), (0, _BUCKET_SIZE)]:
            asyncio.create_task(_report_covered(wx + _dx, wy + _dy))

        # Merge raw readings (keep highest temp per cell)
        for r in scan_result.raw_readings:
            key = (int(round(r["x"])), int(round(r["y"])))
            all_temps[key] = max(all_temps.get(key, 0.0), r.get("temp_celsius", 0.0))

        # Merge detections (keep highest confidence per cell)
        for sig in scan_result.detections:
            key = (sig.x, sig.y)
            if key not in all_detections or sig.confidence > all_detections[key].confidence:
                all_detections[key] = sig

        if on_scan_complete:
            await on_scan_complete(drone, scan_result)

    aborted = visited < len(waypoints)
    merged_raw = [
        {"x": x, "y": y, "temp_celsius": round(temp, 1)}
        for (x, y), temp in all_temps.items()
    ]

    logger.info(
        "search_area: %s visited %d/%d waypoints, found %d survivor(s), battery=%.1f%%",
        drone.id, visited, len(waypoints), len(all_detections), drone.battery,
    )
    return SearchResult(
        drone_id=drone.id,
        waypoints_visited=visited,
        waypoints_total=len(waypoints),
        survivors_detected=len(all_detections) > 0,
        detections=list(all_detections.values()),
        raw_readings=merged_raw,
        battery_remaining_pct=drone.battery,
        aborted=aborted,
        abort_reason="Battery critical." if aborted else None,
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

    if drone.battery_low:
        logger.warning(
            "deliver_aid refused — battery low (%.1f%%) — return to base to charge first", drone.battery
        )
        return DeliverResult(
            drone_id=drone.id,
            success=False,
            status="failed",
            delivered_to=Position(**drone.position),
            battery_remaining_pct=drone.battery,
            message=f"Battery low ({drone.battery:.1f}%) — return to base to charge before delivering.",
        )

    drone.status = DroneStatus.DELIVERING

    # Transit at MAX_BUILDING_HEIGHT so drone.z never drops below building tops
    # during the approach. Interpolating from BASE_Z=10 down to z=0 mid-flight
    # passes through building height (3–10), causing the drone to ghost through
    # obstacle meshes. Flying flat at z=MAX_BUILDING_HEIGHT keeps the drone above
    # all buildings the whole way; we only descend to the delivery altitude after
    # arriving at the target XY.
    move_result = await move_to(
        drone, x, y, MAX_BUILDING_HEIGHT,
        on_waypoint=on_waypoint,
        moving_status=DroneStatus.DELIVERING,
    )

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

    # Arrived at target XY — descend to requested delivery altitude
    drone.z = z

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

    from drone.core.map_client import map_client
    info = await map_client.fetch_map_info()
    _base_x = int(info.get("base_x", BASE_X))
    _base_y = int(info.get("base_y", BASE_Y))

    # Manhattan distance to base computed upfront — used as eta estimate (Option A).
    # Actual A* path may be longer if obstacles force a detour, but "eta" implies
    # it is an estimate so this is acceptable and standard practice.
    eta = _manhattan(drone.x, drone.y, _base_x, _base_y)

    # Navigate home using A* — avoids obstacles same as move_to/deliver_aid.
    # RETURNING status is used so Map Engine shows the correct state during the trip home.
    move_result = await move_to(
        drone, _base_x, _base_y, BASE_Z,
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
        position=Position(x=_base_x, y=_base_y, z=BASE_Z),
        battery_pct=drone.battery,
        message=f"Drone at base. Charging at {BATTERY_CHARGE_RATE}%/s.",
        eta_seconds=eta,
    )