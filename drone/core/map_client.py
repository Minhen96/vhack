from __future__ import annotations

import logging
import time

import asyncio

import websockets
from websockets import WebSocketClientProtocol

from drone.core.config import MAP_WS_URL
from drone.models.drone import Drone

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class MapEngineClient:
    """Persistent WebSocket connection to Ken's Map Engine.

    All messages share the same envelope:
        { "intention": "<type>", "drone_id": "...", "timestamp": <ms>, ...payload }

    Call connect() once on startup, then use send_* methods after each state change.
    """

    def __init__(self) -> None:
        self._ws: WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(MAP_WS_URL), timeout=3.0
            )
            logger.info("Connected to Map Engine at %s", MAP_WS_URL)
        except (OSError, asyncio.TimeoutError):
            logger.warning("Map Engine not reachable at %s — running without map sync.", MAP_WS_URL)
            self._ws = None

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("Disconnected from Map Engine.")

    async def _send(self, payload: dict) -> None:
        if self._ws is None:
            return
        try:
            import json
            await self._ws.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            logger.warning("Map Engine connection closed — message dropped.")
            self._ws = None
        except Exception:
            logger.exception("Failed to send message to Map Engine.")

    async def send_init_connection(self, drone: Drone) -> None:
        await self._send({
            "intention": "init_connection",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "type": drone.type.value,
            "capabilities": drone.capabilities,
            "position": drone.position,
        })

    async def send_position(self, drone: Drone, distance: int = 0) -> None:
        await self._send({
            "intention": "send_position",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "x": drone.x,
            "y": drone.y,
            "z": drone.z,
            "spherical": drone.spherical,  # {"azimuth": ..., "elevation": ...}
            "eta_ms": distance * 200,  # expected animation duration (200ms per cell)
        })

    async def send_drone_status(self, drone: Drone) -> None:
        await self._send({
            "intention": "send_drone_status",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "status": drone.status.value,
            "battery": drone.battery,
        })

    async def send_survivor_detected(
        self, drone: Drone, x: int, y: int, z: int, confidence: float
    ) -> None:
        await self._send({
            "intention": "survivor_detected",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "x": x,
            "y": y,
            "z": z,
            "confidence": confidence,
        })

    async def send_aid_delivered(self, drone: Drone, x: int, y: int, z: int) -> None:
        await self._send({
            "intention": "aid_delivered",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "x": x,
            "y": y,
            "z": z,
        })


# Singleton — imported and used by routers after startup wires it in.
map_client = MapEngineClient()