from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.deps import get_sim
from backend.simulation import Simulation

router = APIRouter(prefix="/api", tags=["drones"])


@router.get("/drones")
async def get_drones(sim: Annotated[Simulation, Depends(get_sim)]) -> list[dict]:
    return sim.query_drones()
