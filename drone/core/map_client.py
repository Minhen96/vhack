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

        # Local cache of blocked (impassable) grid cells.
        # Populated by grid_snapshot on connect, then patched by grid_update messages.
        # Starts empty — all cells treated as passable until Ken sends data.
        self._blocked: set[tuple[int, int]] = set()

        # Background asyncio task that reads incoming WS messages from Ken.
        self._listener_task: asyncio.Task | None = None

    async def connect(self) -> None:
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(MAP_WS_URL), timeout=3.0
            )
            logger.info("Connected to Map Engine at %s", MAP_WS_URL)
        except (OSError, asyncio.TimeoutError):
            logger.warning("Map Engine not reachable at %s — running without map sync.", MAP_WS_URL)
            self._ws = None

    async def start_listener(self) -> None:
        """Start a background task that reads incoming WS messages from Ken.

        Must be called after connect(). Safe to call when not connected (no-op).

        Ken pushes two message types to the drone:
          grid_snapshot — full blocked-cell list on connect (or after a map reload).
                          Replaces _blocked entirely.
          grid_update   — single-cell passability change (new rubble discovered,
                          debris cleared, another drone entering/leaving a cell).
                          Patches _blocked incrementally.

        The listener keeps _blocked current so A* always uses fresh obstacle data
        without any extra HTTP request.
        """
        if self._ws is None:
            return
        self._listener_task = asyncio.create_task(self._receive_loop())
        logger.info("Map Engine listener started.")

    async def _receive_loop(self) -> None:
        """Continuously read and dispatch incoming messages from Ken's Map Engine."""
        import json
        while self._ws is not None:
            try:
                raw = await self._ws.recv()
                msg = json.loads(raw)
                intention = msg.get("intention")

                if intention == "grid_snapshot":
                    # Full grid state — rebuild the blocked set from scratch.
                    # Ken sends this right after the drone connects so pathfinding
                    # has an accurate map before the first move command arrives.
                    self._blocked = {
                        (int(cell[0]), int(cell[1]))
                        for cell in msg.get("blocked", [])
                    }
                    logger.info("grid_snapshot: %d blocked cell(s) loaded", len(self._blocked))

                elif intention == "grid_update":
                    # Single-cell patch — arrives whenever something changes:
                    # rubble found by scan, debris cleared, another drone moving.
                    cell = (int(msg["x"]), int(msg["y"]))
                    if msg.get("passable", True):
                        self._blocked.discard(cell)
                        logger.debug("grid_update: (%d,%d) passable", *cell)
                    else:
                        self._blocked.add(cell)
                        logger.debug("grid_update: (%d,%d) blocked", *cell)

            except websockets.ConnectionClosed:
                logger.warning("Map Engine WS closed — listener stopping.")
                self._ws = None
                break
            except Exception:
                logger.exception("Unexpected error in map listener — listener stopping.")
                break

    def get_blocked(self) -> set[tuple[int, int]]:
        """Return the current set of impassable (x, y) cells.

        Updated in real-time by the WS listener. Pathfinding calls this before
        each movement step to get the freshest obstacle data with zero I/O cost.

        Returns an empty set if Ken has not yet sent a grid_snapshot — drone
        treats all cells as passable and falls back to straight-line movement.
        """
        return self._blocked

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
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