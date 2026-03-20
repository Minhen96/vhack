"""
Mission API Router
==================
REST endpoints for starting, monitoring, and resetting rescue missions.
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from backend.agent.command_agent import get_mission_log, run_mission
from backend.core.drone_registry import registry

router = APIRouter(prefix="/api/mission", tags=["mission"])


class MissionRequest(BaseModel):
    objective: str


class MissionResponse(BaseModel):
    status: str
    output: str | None = None
    error: str | None = None
    log: list[dict] | None = None


# --------------------------------------------------------------------------
# POST /api/mission/start
# --------------------------------------------------------------------------


@router.post("/start", response_model=MissionResponse)
async def start_mission(req: MissionRequest):
    """
    Launch a rescue mission with the given objective.

    Example objectives:
      - "Search the entire disaster zone for survivors and deliver aid."
      - "Scan the South-East quadrant for thermal signatures."
      - "Perform a full grid sweep with all available drones."
    """
    result = await run_mission(req.objective)
    return result


# --------------------------------------------------------------------------
# POST /api/mission/start-background
# --------------------------------------------------------------------------

_background_task: asyncio.Task | None = None
_background_result: dict | None = None


@router.post("/start-background")
async def start_mission_background(req: MissionRequest):
    """Start a mission in the background — poll /api/mission/log for progress."""
    global _background_task, _background_result  # noqa: PLW0603

    if _background_task and not _background_task.done():
        return {"status": "error", "error": "A mission is already running."}

    _background_result = None

    async def _run():
        global _background_result  # noqa: PLW0603
        _background_result = await run_mission(req.objective)

    _background_task = asyncio.create_task(_run())
    return {"status": "started", "message": "Mission launched. Poll /api/mission/log for updates."}


# --------------------------------------------------------------------------
# GET /api/mission/log
# --------------------------------------------------------------------------


@router.get("/log")
async def mission_log():
    """Return the current or most recent mission log."""
    log = get_mission_log()
    if log is None:
        return {"status": "no_mission", "message": "No mission has been started yet."}
    return log


# --------------------------------------------------------------------------
# GET /api/mission/result
# --------------------------------------------------------------------------


@router.get("/result")
async def mission_result():
    """Return the final result of a background mission."""
    if _background_result is not None:
        return _background_result
    if _background_task and not _background_task.done():
        return {"status": "running", "message": "Mission still in progress."}
    return {"status": "no_mission"}


# --------------------------------------------------------------------------
# POST /api/mission/stop
# --------------------------------------------------------------------------


@router.post("/stop")
async def stop_mission():
    """Signal the running mission to stop gracefully."""
    from backend.agent.command_agent import get_mission_log
    from backend.events import push as push_event

    log = get_mission_log()
    if log is None or not log.get("is_running"):
        return {"status": "error", "error": "No mission is currently running."}

    await push_event({"type": "mission_stop"})
    return {"status": "ok", "message": "Stop signal sent. Mission will finish current operations and halt."}


# --------------------------------------------------------------------------
# POST /api/mission/reset
# --------------------------------------------------------------------------


@router.post("/reset")
async def reset_mission():
    """Reset the drone fleet to initial state for a new mission."""
    registry.reset()
    return {"status": "reset", "message": "Drone fleet reset to initial state."}
