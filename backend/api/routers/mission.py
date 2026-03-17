from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.schemas import CommandResult
from backend.core.deps import get_manager, get_sim
from backend.core.ws import ConnectionManager
from backend.models.mission import ScenarioKey
from backend.simulation import Simulation

router = APIRouter(prefix="/api/mission", tags=["mission"])


class MissionStartRequest(BaseModel):
    scenario: ScenarioKey = ScenarioKey.EARTHQUAKE_ALPHA


@router.get("")
async def get_mission(sim: Annotated[Simulation, Depends(get_sim)]) -> dict:
    return sim.query_mission_status()


@router.post("/start", response_model=CommandResult)
async def start_mission(
    req: MissionStartRequest,
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> CommandResult:
    if sim.mission.active:
        raise HTTPException(status_code=409, detail="Mission already active.")
    try:
        sim.load_scenario(req.scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    sim.start()
    await manager.broadcast({"event": "mission_started", "data": sim.mission.to_dict()})
    return CommandResult(success=True, detail=f"Mission started: {req.scenario.value}")


@router.post("/pause", response_model=CommandResult)
async def pause_mission(
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> CommandResult:
    if not sim.mission.active:
        raise HTTPException(status_code=409, detail="No active mission to pause.")
    sim.pause()
    await manager.broadcast({"event": "mission_paused", "data": {}})
    return CommandResult(success=True, detail="Mission paused.")


@router.post("/resume", response_model=CommandResult)
async def resume_mission(
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> CommandResult:
    if not sim.mission.active:
        raise HTTPException(status_code=409, detail="No active mission to resume.")
    sim.resume()
    await manager.broadcast({"event": "mission_resumed", "data": {}})
    return CommandResult(success=True, detail="Mission resumed.")


@router.post("/reset", response_model=CommandResult)
async def reset_mission(
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> CommandResult:
    sim.stop()
    sim.load_scenario(ScenarioKey.EARTHQUAKE_ALPHA)
    await manager.broadcast({"event": "mission_reset", "data": {}})
    return CommandResult(success=True, detail="Mission reset to EARTHQUAKE_ALPHA.")
