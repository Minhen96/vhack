from __future__ import annotations

import logging
import time

import asyncio

import httpx
import websockets
from websockets import WebSocketClientProtocol

from drone.core.config import MAP_WS_URL, SIM_SERVER_URL
from drone.models.drone import Drone

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class MapEngineClient:
    """Persistent WebSocket connection to Map Engine (sim server).

    Message field conventions:
      Outbound (drone → sim server): use "type" field — matches what hub and UI expect.
      Inbound  (sim server → drone): use "intention" field — read in _receive_loop.

    Call connect() once on startup, then use send_* methods after each state change.
    """

    def __init__(self) -> None:
        self._ws: WebSocketClientProtocol | None = None
        # Drone ID stored here so reconnect logic can include it in the URL,
        # allowing hub.go to track and broadcast the correct drone_id on disconnect.
        self._drone_id: str = ""

        # Local cache of blocked (impassable) grid cells.
        # Populated by grid_snapshot on connect, then patched by grid_update messages.
        # Starts empty — all cells treated as passable until map engine sends data.
        self._blocked: set[tuple[int, int]] = set()

        # Rolling buffer of passive heat readings from waypoint scans.
        # Populated by passive_waypoint_scan (called fire-and-forget at each movement
        # step). Capped at 50 entries — older readings are evicted.
        # thermal_scan merges these with its active /scan results so readings picked
        # up while flying are not lost.
        self._recent_heat: list[dict] = []

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

        # Cached map bounds and base position fetched from sim server on first call.
        self._map_info: dict | None = None

    async def connect(self, drone_id: str = "") -> None:
        if drone_id:
            self._drone_id = drone_id
        # Include drone_id as a query param so hub.go can associate this WebSocket
        # connection with the drone's real ID. Without this, hub.go generates a
        # random ID and broadcasts drone_disconnected with the wrong ID on shutdown.
        url = f"{MAP_WS_URL}?drone_id={self._drone_id}" if self._drone_id else MAP_WS_URL
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(url), timeout=3.0
            )
            logger.info("Connected to Map Engine at %s", url)
        except (OSError, asyncio.TimeoutError):
            logger.warning("Map Engine not reachable at %s — running without map sync.", url)
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
                        (int(cell["x"]), int(cell["y"]))
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

    def add_heat_readings(self, readings: list[dict]) -> None:
        """Add thermal readings from a waypoint passive scan to the rolling buffer.

        Called fire-and-forget from passive_waypoint_scan after each movement step.
        Capped at 50 entries — oldest evicted when full.
        """
        self._recent_heat.extend(readings)
        if len(self._recent_heat) > 50:
            self._recent_heat = self._recent_heat[-50:]

    def get_recent_heat(self) -> list[dict]:
        """Return the rolling buffer of passive heat readings from waypoint scans.

        Each entry is {"x": float, "y": float, "temp_celsius": float}.
        thermal_scan merges these with its active /scan results so readings
        picked up while flying are not lost.
        """
        return list(self._recent_heat)

    async def fetch_map_info(self) -> dict:
        """Return map bounds and base position from the sim server.

        Fetched once on first call and cached for the lifetime of the process.
        Falls back to hardcoded defaults if the sim server is unreachable.
        """
        if self._map_info is not None:
            return self._map_info
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{SIM_SERVER_URL}/map-info", timeout=3.0)
                self._map_info = resp.json()
                logger.info("map_info loaded from sim server: %s", self._map_info)
        except Exception:
            from drone.constants import BASE_X, BASE_Y, MAP_X_MAX, MAP_X_MIN, MAP_Y_MAX, MAP_Y_MIN
            self._map_info = {
                "x_min": MAP_X_MIN, "x_max": MAP_X_MAX,
                "y_min": MAP_Y_MIN, "y_max": MAP_Y_MAX,
                "base_x": BASE_X, "base_y": BASE_Y,
            }
            logger.warning("Could not reach sim server for map-info — using hardcoded fallback.")
        return self._map_info

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
            "type": "init_connection",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "drone_type": drone.type.value,
            "capabilities": drone.capabilities,
            "position": drone.position,
        })

    async def send_position(self, drone: Drone, distance: int = 0) -> None:
        await self._send({
            "type": "send_position",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "x": drone.x,
            "y": drone.y,
            "z": drone.z,
            "spherical": drone.spherical,
            "status": drone.status.value.upper(),
            "battery": drone.battery,
            "eta_ms": distance * 200,  # expected animation duration (200ms per cell)
            "drone_type": drone.type.value,  # included so cached replay carries type info
        })

    async def send_drone_status(self, drone: Drone) -> None:
        await self._send({
            "type": "send_drone_status",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "status": drone.status.value,
            "battery": drone.battery,
        })

    async def send_survivor_detected(
        self, drone: Drone, x: int, y: int, z: int, confidence: float
    ) -> None:
        await self._send({
            "type": "survivor_detected",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "x": x,
            "y": y,
            "z": z,
            "confidence": confidence,
        })

    async def send_scan_heatmap(self, drone: Drone, readings: list[dict]) -> None:
        """Send all raw thermal readings to the hub for heatmap rendering in the UI.

        readings is the full unfiltered list from thermal_scan — includes both
        survivor heat (>30°C) and background heat (buildings, ground).
        Hub broadcasts this to UI clients so ThermalHeatmap can colour the ground.
        """
        await self._send({
            "type": "scan_heatmap",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "readings": readings,
        })

    async def send_aid_delivered(self, drone: Drone, x: int, y: int, z: int) -> None:
        await self._send({
            "type": "aid_delivered",
            "drone_id": drone.id,
            "timestamp": _now_ms(),
            "x": x,
            "y": y,
            "z": z,
        })


# Singleton — imported and used by routers after startup wires it in.
map_client = MapEngineClient()