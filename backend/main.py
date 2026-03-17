from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.models.mission import ScenarioKey
from backend.routers import drones, map, mission, survivors, ws
from backend.simulation import Simulation
from backend.ws import ConnectionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    manager = ConnectionManager()
    sim = Simulation()
    sim.set_broadcast(manager.broadcast)

    # load dummy scenario
    sim.load_scenario(ScenarioKey.EARTHQUAKE_ALPHA)

    app.state.sim = sim
    app.state.manager = manager

    logger.info("Application startup complete.")
    yield
    sim.stop()
    logger.info("Application shutdown complete.")


app = FastAPI(title="Rescue Swarm API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(map.router)
app.include_router(drones.router)
app.include_router(survivors.router)
app.include_router(mission.router)
app.include_router(ws.router)
