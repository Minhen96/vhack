from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from drone.api.routers.drones import router as drone_router
from drone.core.config import DRONE_HOST, DRONE_ID, DRONE_PORT, DRONE_TYPE
from drone.core.map_client import map_client
from drone.core.registration import deregister_from_mcp, register_to_mcp
from drone.models.drone import Drone, DroneType
from drone.registry import set_drone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────

    # 1. Initialise the drone for this process
    drone = Drone(id=DRONE_ID, type=DroneType(DRONE_TYPE))
    set_drone(drone)
    logger.info("Drone initialised: id=%s type=%s", drone.id, drone.type.value)

    # 2. Register to MCP server
    await register_to_mcp()

    # 3. Connect WebSocket to Map Engine and announce presence
    await map_client.connect()
    await map_client.send_init_connection(drone)

    # 4. Start listening for incoming messages from map engine (grid_snapshot, grid_update)
    #    so the drone always has a fresh obstacle map for pathfinding.
    await map_client.start_listener()

    logger.info("Drone server ready — %s:%d", DRONE_HOST, DRONE_PORT)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────

    # when the app stops, run this part
    await deregister_from_mcp()
    await map_client.close()

    logger.info("Drone server shut down.")


app = FastAPI(title="Rescue Drone", version="1.0.0", lifespan=lifespan)
app.include_router(drone_router)