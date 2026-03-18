from __future__ import annotations

import heapq


def astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """A* pathfinding on a 4-directional 2D grid.

    Returns an ordered list of (x, y) waypoints from start to goal,
    NOT including the start position itself.

    Returns an empty list when:
    - start == goal (already there, nothing to do)
    - no path exists (goal is surrounded by blocked cells)

    The caller (move_to) treats an empty return as "blocked" and stops
    movement, returning that status to the LLM so it can re-plan.

    Uses Manhattan distance as the heuristic — consistent with the
    4-directional grid, so the result is always optimal.
    """
    if start == goal:
        return []

    # Min-heap entries: (f_score, g_score, node)
    # f = g + h,  g = cost from start,  h = Manhattan distance to goal
    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0, 0, start))

    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start: 0}

    def h(node: tuple[int, int]) -> int:
        return abs(node[0] - goal[0]) + abs(node[1] - goal[1])

    while open_heap:
        _, g, current = heapq.heappop(open_heap)

        if current == goal:
            # Reconstruct the path by tracing came_from back to start
            path: list[tuple[int, int]] = []
            node = current
            while node in came_from:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return path

        # Skip stale heap entries (a shorter path to this node was found earlier)
        if g > g_score.get(current, float("inf")):
            continue

        x, y = current
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if neighbor in blocked:
                continue
            new_g = g + 1
            if new_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = new_g
                came_from[neighbor] = current
                heapq.heappush(open_heap, (new_g + h(neighbor), new_g, neighbor))

    # No path found — goal is unreachable from start
    return []