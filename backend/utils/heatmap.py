from __future__ import annotations

from typing import TYPE_CHECKING

from backend.constants import (
    HEATMAP_DECAY_RATE,
    HEATMAP_DETECT_BOOST,
    HEATMAP_NEIGHBOR_BOOST,
    GRID_SIZE,
)

if TYPE_CHECKING:
    from backend.models.grid import Cell


def _manhattan(ax: int, ay: int, bx: int, by: int) -> int:
    return abs(ax - bx) + abs(ay - by)


def _get_neighbors(
    grid: list[list[Cell]],
    x: int,
    y: int,
    radius: int,
) -> list[Cell]:
    neighbors: list[Cell] = []
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    for ny in range(max(0, y - radius), min(rows, y + radius + 1)):
        for nx in range(max(0, x - radius), min(cols, x + radius + 1)):
            if nx == x and ny == y:
                continue
            neighbors.append(grid[ny][nx])
    return neighbors


def update_on_detection(
    grid: list[list[Cell]],
    x: int,
    y: int,
    confidence: float,
    radius: int = 2,
) -> set[tuple[int, int]]:
    """
    Boost probability at (x, y) and surrounding cells when a thermal
    signal is detected.

    Returns set of (x, y) cells whose probability changed.
    """
    dirty: set[tuple[int, int]] = set()

    cell = grid[y][x]
    cell.probability = min(1.0, cell.probability + HEATMAP_DETECT_BOOST * confidence)
    dirty.add((x, y))

    for neighbor in _get_neighbors(grid, x, y, radius):
        dist = _manhattan(x, y, neighbor.x, neighbor.y)
        if dist == 0:
            continue
        boost = (HEATMAP_NEIGHBOR_BOOST / dist) * confidence
        neighbor.probability = min(1.0, neighbor.probability + boost)
        dirty.add((neighbor.x, neighbor.y))

    return dirty


def decay_all(grid: list[list[Cell]]) -> None:
    """
    Apply time decay to all non-confirmed cells each tick.
    Confirmed survivors are never decayed.
    """
    for row in grid:
        for cell in row:
            if not cell.survivor:
                cell.probability *= HEATMAP_DECAY_RATE


def mark_cleared(grid: list[list[Cell]], x: int, y: int) -> None:
    """Hard-reset probability for a cell confirmed to have no survivor."""
    cell = grid[y][x]
    cell.probability = 0.0
    cell.searched = True


def get_highest_probability_cells(
    grid: list[list[Cell]],
    top_n: int = 5,
    min_prob: float = 0.1,
) -> list[tuple[float, int, int]]:
    """
    Returns top_n unsearched cells sorted by probability descending.
    Format: [(probability, x, y), ...]
    """
    candidates: list[tuple[float, int, int]] = []
    for row in grid:
        for cell in row:
            if not cell.searched and cell.probability >= min_prob and cell.passable:
                candidates.append((cell.probability, cell.x, cell.y))
    candidates.sort(reverse=True)
    return candidates[:top_n]
