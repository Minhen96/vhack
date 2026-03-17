from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.agent import run_agent_loop
from backend.api.routers import drones, map, mission, survivors, websocket
from backend.core.websocket import ConnectionManager
from backend.models.mission import ScenarioKey
from backend.simulation import Simulation

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
    sim.load_scenario(ScenarioKey.EARTHQUAKE_ALPHA)

    app.state.sim = sim
    app.state.manager = manager

    # Agent loop runs independently (slow LLM response never freezes the sim)
    agent_task = asyncio.create_task(run_agent_loop(sim, manager.broadcast))

    logger.info("Application startup complete.")
    yield

    agent_task.cancel()
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
app.include_router(websocket.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )
