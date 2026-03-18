from __future__ import annotations

import logging
import math
import random
from collections.abc import Awaitable, Callable

from drone.constants import (
    BASE_X,
    BASE_Y,
    BASE_Z,
    BATTERY_DRAIN_DELIVER,
    BATTERY_DRAIN_PER_CELL,
    BATTERY_DRAIN_SCAN,
    SCAN_RADIUS_DEFAULT,
)
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
      a WS position event to Ken for smooth map animation.

    Returns:
      "arrived" — reached (x, y, z) successfully.
      "blocked" — battery critical OR no passable path exists; drone stays put.
    """
    if drone.battery_critical:
        logger.warning("move_to refused — battery critical (%.1f%%)", drone.battery)
        return MoveResult(status="blocked", position=Position(**drone.position))

    # Import here to avoid a top-level circular import (map_client imports drone models)
    from drone.core.map_client import map_client

    goal = (x, y)
    steps = 0

    while (drone.x, drone.y) != goal:
        if drone.battery_critical:
            logger.warning("move_to aborted mid-path — battery critical (%.1f%%)", drone.battery)
            return MoveResult(status="blocked", position=Position(**drone.position))

        # Re-plan every step using the latest WS-cached obstacle data.
        # Since Ken pushes grid_update messages in real-time, _blocked reflects
        # any map changes that happened while the drone was walking earlier steps.
        path = astar((drone.x, drone.y), goal, map_client.get_blocked())

        if not path:
            # A* found no route — goal is unreachable from current position.
            logger.warning(
                "move_to: no path from (%d,%d) to (%d,%d) — blocked",
                drone.x, drone.y, x, y,
            )
            return MoveResult(status="blocked", position=Position(**drone.position))

        # Take only the immediate next step, then re-plan (rolling-horizon approach).
        # This is what makes the drone fully reactive: it never commits to a full
        # path upfront; it rechecks the map before every single cell move.
        wx, wy = path[0]
        step_dist = _manhattan(drone.x, drone.y, wx, wy)
        _drain(drone, step_dist * BATTERY_DRAIN_PER_CELL)

        # Update azimuth to face the direction of travel
        dx, dy = wx - drone.x, wy - drone.y
        if dx != 0 or dy != 0:
            drone.azimuth = math.degrees(math.atan2(-dy, dx)) % 360

        drone.x, drone.y, drone.z = wx, wy, z
        drone.status = DroneStatus.MOVING
        steps += 1

        # Push per-step position update so Ken's map shows the drone moving
        # cell-by-cell. step_dist drives eta_ms for smooth animation lerp.
        if on_waypoint:
            await on_waypoint(drone, step_dist)

    drone.status = DroneStatus.IDLE
    logger.info(
        "move_to: %s arrived at (%d, %d, %d) in %d step(s), battery=%.1f%%",
        drone.id, x, y, z, steps, drone.battery,
    )
    return MoveResult(status="arrived", position=Position(x=x, y=y, z=z))


async def thermal_scan(drone: Drone, radius: int = SCAN_RADIUS_DEFAULT) -> ScanResult:
    if not drone.has_capability("thermal_scan"):
        logger.warning("thermal_scan refused — drone %s (type=%s) lacks capability", drone.id, drone.type)
        return ScanResult(
            survivors=[],
            scan_area=ScanArea(cx=drone.x, cy=drone.y, r=radius),
        )

    if drone.battery_critical:
        logger.warning("thermal_scan refused — battery critical (%.1f%%)", drone.battery)
        return ScanResult(
            survivors=[],
            scan_area=ScanArea(cx=drone.x, cy=drone.y, r=radius),
        )

    drone.status = DroneStatus.SCANNING
    _drain(drone, BATTERY_DRAIN_SCAN)

    # TODO: replace with real grid data from Map Engine once the
    # GET /grid/passability (or equivalent) endpoint is available.
    # For now, simulate a 10% chance of a survivor signal per cell in radius.
    survivors: list[SurvivorSignal] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            nx, ny = drone.x + dx, drone.y + dy
            if random.random() < 0.1:
                confidence = round(random.uniform(0.7, 1.0), 3)
                survivors.append(SurvivorSignal(x=nx, y=ny, confidence=confidence))

    drone.status = DroneStatus.IDLE

    logger.info(
        "thermal_scan: %s scanned r=%d from (%d, %d), found %d signal(s)",
        drone.id, radius, drone.x, drone.y, len(survivors),
    )
    return ScanResult(
        survivors=survivors,
        scan_area=ScanArea(cx=drone.x, cy=drone.y, r=radius),
    )


async def deliver_aid(drone: Drone, x: int, y: int, z: int = 0) -> DeliverResult:
    if not drone.has_capability("deliver_aid"):
        logger.warning("deliver_aid refused — drone %s (type=%s) lacks capability", drone.id, drone.type)
        return DeliverResult(status="failed", location=Position(**drone.position))

    if drone.battery_critical:
        logger.warning("deliver_aid refused — battery critical (%.1f%%)", drone.battery)
        return DeliverResult(status="failed", location=Position(**drone.position))

    drone.status = DroneStatus.DELIVERING

    # Move to target first
    distance = _manhattan(drone.x, drone.y, x, y)
    _drain(drone, distance * BATTERY_DRAIN_PER_CELL)
    drone.x, drone.y, drone.z = x, y, z

    # Deliver
    _drain(drone, BATTERY_DRAIN_DELIVER)
    drone.status = DroneStatus.IDLE

    logger.info("deliver_aid: %s delivered at (%d, %d, %d), battery=%.1f%%", drone.id, x, y, z, drone.battery)
    return DeliverResult(status="delivered", location=Position(x=x, y=y, z=z))


async def get_battery_status(drone: Drone) -> BatteryResult:
    return BatteryResult(
        drone_id=drone.id,
        battery=drone.battery,
        charging=drone.is_charging,
    )


async def get_drone_status(drone: Drone) -> StatusResult:
    return StatusResult(
        drone_id=drone.id,
        status=drone.status.value,
        position=Position(**drone.position),
        battery=drone.battery,
    )


async def return_to_base(drone: Drone) -> ReturnResult:
    if drone.status == DroneStatus.CHARGING:
        return ReturnResult(status="arrived", eta_seconds=0)

    distance = _manhattan(drone.x, drone.y, BASE_X, BASE_Y)
    _drain(drone, distance * BATTERY_DRAIN_PER_CELL)

    drone.x, drone.y, drone.z = BASE_X, BASE_Y, BASE_Z
    drone.status = DroneStatus.CHARGING
    drone.battery = 100.0

    logger.info("return_to_base: %s returned to base, fully charged", drone.id)
    return ReturnResult(status="arrived", eta_seconds=distance)
