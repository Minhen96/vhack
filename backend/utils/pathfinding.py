from __future__ import annotations

import heapq
from typing import TYPE_CHECKING

from backend.core.config import (
    RISK_DEBRIS_PER_LEVEL,
    RISK_FIRE_PENALTY,
    RISK_WATER_PENALTY,
    RISK_DRONE_SOFT_PENALTY,
)

if TYPE_CHECKING:
    from backend.models.grid import Cell


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Manhattan distance heuristic."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _cell_cost(
    cell: Cell,
    occupied: set[tuple[int, int]],
    hard_blocked: set[tuple[int, int]] | None = None,
) -> float:
    """Movement cost for entering a cell."""
    if not cell.passable or (hard_blocked and (cell.x, cell.y) in hard_blocked):
        return RISK_WATER_PENALTY

    cost = 1.0
    cost += cell.debris_level * RISK_DEBRIS_PER_LEVEL

    if cell.fire:
        cost += RISK_FIRE_PENALTY

    if (cell.x, cell.y) in occupied:
        cost += RISK_DRONE_SOFT_PENALTY

    return cost


def find_path(
    grid: list[list[Cell]],
    start: tuple[int, int],
    goal: tuple[int, int],
    occupied: set[tuple[int, int]] | None = None,
    hard_blocked: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """
    A* pathfinding with risk-weighted costs.

    Args:
        grid:         2-D grid indexed as grid[y][x].
        start:        (x, y) starting position.
        goal:         (x, y) destination.
        occupied:     cells softly penalised (other drones).
        hard_blocked: cells treated as impassable (e.g. idle drones on a replan).

    Returns:
        Ordered list of (x, y) steps from start (exclusive) to goal (inclusive).
        Empty list if no path exists.
    """
    if occupied is None:
        occupied = set()

    rows = len(grid)
    cols = len(grid[0]) if rows else 0

    def in_bounds(x: int, y: int) -> bool:
        return 0 <= x < cols and 0 <= y < rows

    if start == goal:
        return []

    # (f_score, tie_breaker, position)
    counter = 0
    open_heap: list[tuple[float, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0.0, counter, start))

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start: 0.0}

    while open_heap:
        _, _, current = heapq.heappop(open_heap)

        if current == goal:
            path: list[tuple[int, int]] = []
            node = current
            while node in came_from:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        cx, cy = current
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = cx + dx, cy + dy
            if not in_bounds(nx, ny):
                continue

            neighbor_cell = grid[ny][nx]
            cost = _cell_cost(neighbor_cell, occupied, hard_blocked)
            if cost >= RISK_WATER_PENALTY:
                continue  # impassable

            tentative_g = g_score[current] + cost
            neighbor = (nx, ny)

            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + _heuristic(neighbor, goal)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbor))

    return []  # no path found
