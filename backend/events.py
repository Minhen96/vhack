"""
Drone Event Queue
=================
Shared in-process asyncio queue.  Drone processes POST to /internal/event
when something notable happens; the MCP wait_for_event tool reads from here.

Event shapes
------------
  survivor_found   {type, drone_id, x, y, confidence}
  battery_low      {type, drone_id, battery}
  search_complete  {type, drone_id, waypoints_visited, waypoints_total,
                    survivors_found, aborted, abort_reason, battery_remaining_pct}
"""

import asyncio

_queue: asyncio.Queue[dict] = asyncio.Queue()


async def push(event: dict) -> None:
    """Push an event from a drone into the queue."""
    await _queue.put(event)


async def wait(timeout: float = 30.0) -> dict | None:
    """Block until an event arrives, or return None on timeout."""
    try:
        return await asyncio.wait_for(_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


def clear() -> int:
    """Drain and discard all pending events — call at mission start to flush stale entries.

    Drone processes push drone_joined events when they register on startup.
    If the mission agent starts after the drones are already running, those
    startup events are still sitting in the queue. Clearing here prevents the
    LLM from seeing stale drone_joined events mid-mission.

    Returns the number of events discarded.
    """
    discarded = 0
    while not _queue.empty():
        try:
            _queue.get_nowait()
            discarded += 1
        except asyncio.QueueEmpty:
            break
    return discarded