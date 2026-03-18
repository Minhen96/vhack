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
    """Persistent WebSocket connection to Map Engine.

    All messages share the same envelope:
        { "intention": "<type>", "drone_id": "...", "timestamp": <ms>, ...payload }

    Call connect() once on startup, then use send_* methods after each state change.
    """

    def __init__(self) -> None:
        self._ws: WebSocketClientProtocol | None = None

        # Local cache of blocked (impassable) grid cells.
        # Populated by grid_snapshot on connect, then patched by grid_update messages.
        # Starts empty — all cells treated as passable until map engine sends data.
        self._blocked: set[tuple[int, int]] = set()

        # Background asyncio task that reads incoming WS messages from map engine.
        self._listener_task: asyncio.Task | None = None

        # Background asyncio task that drains _send_queue one message at a time.
        # Ensures only one send() is in-flight at any moment — WebSocket is a single
        # tube and parallel sends corrupt the stream.
        self._pump_task: asyncio.Task | None = None

        # All outbound messages are enqueued here; the write pump sends them serially.
        # Capped at 256 — if the queue is full (map engine unreachable for a long time),
        # the oldest message is discarded rather than growing memory unboundedly.
        self._send_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=256)

        # Drone reference stored on first send_init_connection so the receive loop
        # can re-announce the drone to Map Engine after a reconnect without needing it passed in.
        self._drone: Drone | None = None

    async def connect(self) -> None:
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(MAP_WS_URL), timeout=3.0
            )
            logger.info("Connected to Map Engine at %s", MAP_WS_URL)
        except (OSError, asyncio.TimeoutError):
            logger.warning("Map Engine not reachable at %s — running without map sync.", MAP_WS_URL)
            self._ws = None

    async def _write_pump(self) -> None:
        """Drain _send_queue and send messages one-at-a-time over the WebSocket.

        A WebSocket is a single TCP tube — concurrent sends corrupt the stream.
        All _send() calls enqueue here; this pump serialises them.
        Messages queued while disconnected are dropped (same behaviour as before).
        """
        import json
        while True:
            try:
                payload = await self._send_queue.get()
                if self._ws is not None:
                    try:
                        await self._ws.send(json.dumps(payload))
                    except websockets.ConnectionClosed:
                        logger.warning("Map Engine connection closed — message dropped.")
                        self._ws = None
                    except Exception:
                        logger.exception("Failed to send message to Map Engine.")
                self._send_queue.task_done()
            except asyncio.CancelledError:
                break

    async def start_listener(self) -> None:
        """Start a background task that reads incoming WS messages from map engine.

        Safe to call even when not currently connected — the receive loop handles
        reconnection internally and will keep retrying until the app shuts down.

        Map engine pushes two message types to the drone:
          grid_snapshot — full blocked-cell list on connect (or after a map reload).
                          Replaces _blocked entirely.
          grid_update   — single-cell passability change (new rubble discovered,
                          debris cleared, another drone entering/leaving a cell).
                          Patches _blocked incrementally.

        The listener keeps _blocked current so A* always uses fresh obstacle data
        without any extra HTTP request.
        """
        self._listener_task = asyncio.create_task(self._receive_loop())
        self._pump_task = asyncio.create_task(self._write_pump())
        logger.info("Map Engine listener and write pump started.")

    async def _receive_loop(self) -> None:
        """Continuously read messages from map engine, reconnecting on disconnect.

        Reconnect logic:
        - On connection drop, waits 5 seconds then retries connect().
        - Retries indefinitely until the app shuts down (close() cancels this task).
        - On reconnect, map engine should push a fresh grid_snapshot automatically.
        """
        import json
        while True:
            if self._ws is None:
                # Connection lost — wait then try to reconnect
                logger.info("Map Engine listener: retrying connection in 5s...")
                await asyncio.sleep(5.0)
                await self.connect()
                if self._ws is None:
                    continue   # still not up, loop and wait again
                logger.info("Map Engine reconnected — resuming listener.")
                # Re-announce the drone so Map Engine knows who this connection belongs to.
                # Without this, Map Engine has no record of this drone after its restart.
                if self._drone:
                    await self.send_init_connection(self._drone)

            try:
                raw = await self._ws.recv()
                msg = json.loads(raw)
                intention = msg.get("intention")

                if intention == "grid_snapshot":
                    # Full grid state — rebuild the blocked set from scratch.
                    # Map engine sends this right after the drone connects so pathfinding
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
                logger.warning("Map Engine WS closed — will reconnect in 5s.")
                self._ws = None
                # loop continues — reconnect block at top will handle it
            except asyncio.CancelledError:
                # close() cancelled this task — exit cleanly
                break
            except Exception:
                logger.exception("Unexpected error in map listener.")
                self._ws = None

    def get_blocked(self) -> set[tuple[int, int]]:
        """Return the current set of impassable (x, y) cells.

        Updated in real-time by the WS listener. Pathfinding calls this before
        each movement step to get the freshest obstacle data with zero I/O cost.

        Returns an empty set if map engine has not yet sent a grid_snapshot — drone
        treats all cells as passable and falls back to straight-line movement.
        """
        return self._blocked

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pump_task:
            self._pump_task.cancel()
            self._pump_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
            logger.info("Disconnected from Map Engine.")

    async def _send(self, payload: dict) -> None:
        """Enqueue a message for serialised delivery via the write pump.

        If the queue is full (map engine unreachable for too long), the oldest
        message is dropped to make room — stale telemetry is worthless anyway.
        """
        if self._send_queue.full():
            try:
                self._send_queue.get_nowait()
                self._send_queue.task_done()
                logger.warning("Send queue full — oldest message dropped.")
            except asyncio.QueueEmpty:
                pass
        await self._send_queue.put(payload)

    async def send_init_connection(self, drone: Drone) -> None:
        # Store drone ref so the reconnect loop can re-announce without needing it passed in
        self._drone = drone
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