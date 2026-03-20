from __future__ import annotations

import heapq


def astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]],
    bounds: tuple[int, int, int, int] | None = None,
) -> list[tuple[int, int]]:
    """Find the shortest path from start to goal, avoiding blocked cells.

    A* is like a smart explorer — instead of blindly checking every cell,
    it always explores the cell that looks most promising next.

    Each cell gets a score:
        f = g + h
        g = actual steps walked from start to this cell
        h = estimated steps still needed to reach goal (Manhattan distance)

    The cell with the lowest f score is explored first — meaning A* always
    follows the path that is both short so far AND heading toward the goal.
    This avoids wasting time on paths going in the wrong direction.

    Manhattan distance (h):
        h = |current_x - goal_x| + |current_y - goal_y|
        Counts steps left/right + up/down, ignoring walls.
        Always an underestimate — which keeps the result correct and optimal.

    Returns an ordered list of (x, y) waypoints from start to goal,
    NOT including the start position itself.

    Returns an empty list when:
    - start == goal (already there, nothing to do)
    - no path exists (goal is surrounded by blocked cells)

    The caller (move_to) treats an empty return as "blocked" and stops
    movement, returning that status to the LLM so it can re-plan.
    """
    if start == goal:
        return []

    # A min-heap always gives the smallest item first.
    # Each entry is (f, g, node) — sorted by f so the most promising cell is explored next.
    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    heapq.heappush(open_heap, (0, 0, start))

    # came_from[B] = A means "we reached B by stepping from A"
    # Used at the end to trace the path backwards from goal to start.
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    # g_score[node] = cheapest known cost (steps) to reach this node from start
    g_score: dict[tuple[int, int], int] = {start: 0}

    def h(node: tuple[int, int]) -> int:
        # Manhattan distance — steps left/right + up/down to goal, ignoring walls
        return abs(node[0] - goal[0]) + abs(node[1] - goal[1])

    while open_heap:
        _, g, current = heapq.heappop(open_heap)   # pick lowest f score cell

        if current == goal:
            # Found the goal — trace came_from backwards to reconstruct the path
            path: list[tuple[int, int]] = []
            node = current
            while node in came_from:
                path.append(node)
                node = came_from[node]   # step backwards toward start
            path.reverse()               # was built goal→start, flip to start→goal
            return path

        # The heap can have duplicate entries for the same node.
        # If we already found a cheaper path to this node, skip this stale entry.
        if g > g_score.get(current, float("inf")):
            continue

        # Check all 4 neighbours (no diagonals)
        x, y = current
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if bounds is not None:
                nx, ny = neighbor
                if not (bounds[0] <= nx <= bounds[2] and bounds[1] <= ny <= bounds[3]):
                    continue              # outside map — skip
            if neighbor in blocked:
                continue                  # wall — skip

            new_g = g + 1                 # cost to reach neighbour via current
            if new_g < g_score.get(neighbor, float("inf")):
                # Found a cheaper way to reach this neighbour — record it
                g_score[neighbor] = new_g
                came_from[neighbor] = current
                heapq.heappush(open_heap, (new_g + h(neighbor), new_g, neighbor))

    # Explored every reachable cell and never hit goal — no path exists
    return []