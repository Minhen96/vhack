from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_sim
from backend.simulation import Simulation

router = APIRouter(prefix="/api", tags=["map"])


@router.get("/map")
async def get_map(sim: Annotated[Simulation, Depends(get_sim)]) -> dict:
    return sim.query_map_state()


@router.get("/heatmap")
async def get_heatmap(sim: Annotated[Simulation, Depends(get_sim)]) -> list[list[float]]:
    return sim.query_heatmap()
