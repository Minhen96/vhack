from __future__ import annotations

import math
from collections import deque
from typing import TYPE_CHECKING

from backend.constants import BASE_X, BASE_Y, BASE_COMM_RANGE

if TYPE_CHECKING:
    from backend.models.drone import Drone


def _euclidean(ax: int, ay: int, bx: int, by: int) -> float:
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def can_communicate(a: Drone, b: Drone) -> bool:
    """Two drones can communicate if within range of either."""
    dist = _euclidean(a.x, a.y, b.x, b.y)
    return dist <= max(a.communication_range, b.communication_range)


def _can_reach_base_direct(drone: Drone) -> bool:
    dist = _euclidean(drone.x, drone.y, BASE_X, BASE_Y)
    return dist <= max(drone.communication_range, BASE_COMM_RANGE)


def is_connected_to_base(
    drone: Drone,
    all_drones: list[Drone],
) -> bool:
    """
    BFS through the drone mesh to check whether this drone has a
    communication path back to the base station.
    """
    if _can_reach_base_direct(drone):
        return True

    visited: set[str] = {drone.id}
    queue: deque[Drone] = deque([drone])

    drone_map = {d.id: d for d in all_drones}

    while queue:
        current = queue.popleft()
        for other in all_drones:
            if other.id in visited:
                continue
            if can_communicate(current, other):
                if _can_reach_base_direct(other):
                    return True
                visited.add(other.id)
                queue.append(other)

    return False


def get_isolated_drones(all_drones: list[Drone]) -> list[Drone]:
    """Returns drones with no communication path to base."""
    return [d for d in all_drones if not is_connected_to_base(d, all_drones)]


def find_relay_point(isolated_drone: Drone) -> tuple[int, int]:
    """
    Returns the midpoint between the base station and the isolated drone.
    This is where a relay drone should be stationed.
    """
    rx = (isolated_drone.x + BASE_X) // 2
    ry = (isolated_drone.y + BASE_Y) // 2
    return (rx, ry)


def compute_mesh_health(all_drones: list[Drone]) -> float:
    """Returns fraction (0–1) of active drones connected to base."""
    if not all_drones:
        return 1.0
    connected = sum(
        1 for d in all_drones if is_connected_to_base(d, all_drones)
    )
    return round(connected / len(all_drones), 3)


def get_drone_neighbors(drone: Drone, all_drones: list[Drone]) -> list[Drone]:
    """Returns all drones within communication range of this drone."""
    return [
        other
        for other in all_drones
        if other.id != drone.id and can_communicate(drone, other)
    ]
