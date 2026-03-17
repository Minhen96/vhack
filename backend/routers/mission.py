from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.deps import get_manager, get_sim
from backend.models.mission import ScenarioKey
from backend.simulation import Simulation
from backend.ws import ConnectionManager

router = APIRouter(prefix="/api/mission", tags=["mission"])


class MissionStartRequest(BaseModel):
    scenario: ScenarioKey = ScenarioKey.EARTHQUAKE_ALPHA


@router.get("")
async def get_mission(sim: Annotated[Simulation, Depends(get_sim)]) -> dict:
    return sim.query_mission_status()


@router.post("/start")
async def start_mission(
    req: MissionStartRequest,
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> dict:
    if sim.mission.active:
        raise HTTPException(status_code=400, detail="Mission already active.")
    try:
        sim.load_scenario(req.scenario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sim.start()
    await manager.broadcast({"event": "mission_started", "data": sim.mission.to_dict()})
    return {"success": True, "scenario": req.scenario}


@router.post("/pause")
async def pause_mission(
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> dict:
    sim.pause()
    await manager.broadcast({"event": "mission_paused", "data": {}})
    return {"success": True}


@router.post("/resume")
async def resume_mission(
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> dict:
    sim.resume()
    await manager.broadcast({"event": "mission_resumed", "data": {}})
    return {"success": True}


@router.post("/reset")
async def reset_mission(
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> dict:
    sim.stop()
    sim.load_scenario(ScenarioKey.EARTHQUAKE_ALPHA)
    await manager.broadcast({"event": "mission_reset", "data": {}})
    return {"success": True}
