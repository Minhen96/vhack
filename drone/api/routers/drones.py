from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException

from drone.api.schemas import DeliverRequest, MoveRequest, ScanRequest, SearchRequest
from drone.core.config import MCP_URL
from drone.core.map_client import map_client
from drone.functions import (
    deliver_aid,
    get_battery_status,
    get_drone_status,
    move_to,
    passive_waypoint_scan,
    return_to_base,
    search_area,
    thermal_scan,
)
from drone.models.results import (
    BatteryResult,
    DeliverResult,
    MoveResult,
    ReturnResult,
    ScanResult,
    SearchResult,
    StatusResult,
)
from drone.models.drone import Drone
from drone.registry import get_drone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drones", tags=["drones"])


def _lookup(drone_id: str):
    drone = get_drone()
    if drone is None or drone.id != drone_id:
        raise HTTPException(status_code=404, detail=f"Drone '{drone_id}' not found.")
    return drone


@router.post("/{drone_id}/move", response_model=MoveResult)
async def move(drone_id: str, body: MoveRequest) -> MoveResult:
    drone = _lookup(drone_id)

    # on_waypoint is called inside move_to after each single-cell step.
    # sleep(0.1) paces position updates to ~10/s so the frontend lerp
    # animation has time to render each step rather than teleporting.
    # It also spaces out passive_waypoint_scan HTTP calls so the sim
    # server isn't flooded with dozens of concurrent requests.
    async def on_waypoint(d: Drone, step_dist: int) -> None:
        await map_client.send_position(d, step_dist)
        await map_client.send_drone_status(d)
        asyncio.create_task(passive_waypoint_scan(d))
        await asyncio.sleep(0.1)

    result = await move_to(drone, body.x, body.y, body.z, on_waypoint=on_waypoint)
    # Final status push — sets drone to IDLE (or confirms blocked position).
    # Position was already sent at each waypoint above.
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/scan", response_model=ScanResult)
async def scan(drone_id: str, body: ScanRequest = ScanRequest()) -> ScanResult:
    drone = _lookup(drone_id)
    result = await thermal_scan(drone, body.radius)
    # Send raw readings to UI for heatmap rendering (all temperatures, unfiltered)
    if result.raw_readings:
        await map_client.send_scan_heatmap(drone, result.raw_readings)
    # Notify hub: each survivor signal found (>30°C detections only)
    for signal in result.detections:
        await map_client.send_survivor_detected(drone, signal.x, signal.y, drone.z, signal.confidence)
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/deliver", response_model=DeliverResult)
async def deliver(drone_id: str, body: DeliverRequest) -> DeliverResult:
    drone = _lookup(drone_id)

    # Same as move — stream position updates to Map Engine at each step during approach
    async def on_waypoint(d: Drone, step_dist: int) -> None:
        await map_client.send_position(d, step_dist)
        await map_client.send_drone_status(d)
        asyncio.create_task(passive_waypoint_scan(d))
        await asyncio.sleep(0.1)

    result = await deliver_aid(drone, body.x, body.y, body.z, on_waypoint=on_waypoint)
    # Notify Map Engine: aid delivered at location + final status
    if result.status == "delivered":
        await map_client.send_aid_delivered(drone, body.x, body.y, body.z)
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/return", response_model=ReturnResult)
async def recall(drone_id: str) -> ReturnResult:
    drone = _lookup(drone_id)

    # Stream position updates to Map Engine at each step during the trip home
    async def on_waypoint(d: Drone, step_dist: int) -> None:
        await map_client.send_position(d, step_dist)
        await map_client.send_drone_status(d)
        asyncio.create_task(passive_waypoint_scan(d))
        await asyncio.sleep(0.1)

    # Push live battery updates every second while charging so Map Engine
    # sees the battery rising in real-time without needing to poll
    async def on_tick(d: Drone) -> None:
        await map_client.send_drone_status(d)

    result = await return_to_base(drone, on_waypoint=on_waypoint, on_tick=on_tick)
    # Final status push — charging or blocked
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/search", response_model=SearchResult)
async def search(drone_id: str, body: SearchRequest) -> SearchResult:
    drone = _lookup(drone_id)

    async def on_waypoint(d: Drone, step_dist: int) -> None:
        await map_client.send_position(d, step_dist)
        await map_client.send_drone_status(d)
        asyncio.create_task(passive_waypoint_scan(d))
        await asyncio.sleep(0.1)

    async def on_scan_complete(d: Drone, scan_result: ScanResult) -> None:
        if scan_result.raw_readings:
            await map_client.send_scan_heatmap(d, scan_result.raw_readings)
        for signal in scan_result.detections:
            await map_client.send_survivor_detected(d, signal.x, signal.y, d.z, signal.confidence)
        await map_client.send_drone_status(d)

    result = await search_area(
        drone,
        body.x1, body.y1, body.x2, body.y2,
        body.z, body.step, body.scan_radius,
        on_waypoint=on_waypoint,
        on_scan_complete=on_scan_complete,
    )
    await map_client.send_drone_status(drone)
    return result


# Tracks the active background search task per drone (keyed by drone_id).
# Prevents launching two concurrent searches on the same drone.
_active_searches: dict[str, asyncio.Task] = {}


@router.post("/{drone_id}/start_search")
async def start_search(drone_id: str, body: SearchRequest) -> dict:
    """Launch an autonomous snake-pattern sweep as a background task.

    Returns immediately — the drone sweeps independently.
    Events (survivor_found, battery_low, search_complete) are pushed to the
    backend event queue at MCP_URL/internal/event as they occur.
    """
    drone = _lookup(drone_id)

    existing = _active_searches.get(drone_id)
    if existing and not existing.done():
        return {"started": False, "reason": "Search already in progress."}

    async def _push(event: dict) -> None:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(f"{MCP_URL}/internal/event", json=event, timeout=3.0)
        except Exception:
            logger.warning("start_search: failed to push event %s", event.get("type"))

    async def run_search() -> None:
        reported: set[tuple[int, int]] = set()  # deduplicate survivor events
        battery_low_pushed = False

        async def on_waypoint(d: Drone, step_dist: int) -> None:
            nonlocal battery_low_pushed
            await map_client.send_position(d, step_dist)
            await map_client.send_drone_status(d)

            async def _survivor_cb(x: int, y: int, temp: float) -> None:
                key = (x, y)
                if key not in reported:
                    reported.add(key)
                    confidence = round(min(temp / 37.5, 1.0), 3)
                    # Notify frontend via WebSocket so detected count updates in real-time
                    await map_client.send_survivor_detected(d, x, y, d.z, confidence)
                    await _push({
                        "type": "survivor_found",
                        "drone_id": d.id,
                        "x": x,
                        "y": y,
                        "confidence": confidence,
                    })

            asyncio.create_task(passive_waypoint_scan(d, on_survivor=_survivor_cb))
            await asyncio.sleep(0.1)
            if d.battery_low and not battery_low_pushed:
                battery_low_pushed = True
                await _push({"type": "battery_low", "drone_id": d.id, "battery": d.battery})

        async def on_scan_complete(d: Drone, scan_result: ScanResult) -> None:
            if scan_result.raw_readings:
                await map_client.send_scan_heatmap(d, scan_result.raw_readings)
            for signal in scan_result.detections:
                await map_client.send_survivor_detected(d, signal.x, signal.y, d.z, signal.confidence)
                key = (signal.x, signal.y)
                if key not in reported:
                    reported.add(key)
                    await _push({
                        "type": "survivor_found",
                        "drone_id": d.id,
                        "x": signal.x,
                        "y": signal.y,
                        "confidence": signal.confidence,
                    })
            await map_client.send_drone_status(d)

        result = await search_area(
            drone,
            body.x1, body.y1, body.x2, body.y2,
            body.z, body.step, body.scan_radius,
            on_waypoint=on_waypoint,
            on_scan_complete=on_scan_complete,
        )
        await map_client.send_drone_status(drone)

        # Auto-return to base after sweep (handles both normal completion and battery abort).
        # The LLM does NOT need to call return_to_base — the background task owns the full lifecycle.
        async def _on_return_waypoint(d: Drone, step_dist: int) -> None:
            await map_client.send_position(d, step_dist)
            await map_client.send_drone_status(d)
            await asyncio.sleep(0.1)

        async def _on_charge_tick(d: Drone) -> None:
            await map_client.send_drone_status(d)

        await return_to_base(drone, on_waypoint=_on_return_waypoint, on_tick=_on_charge_tick)
        await map_client.send_drone_status(drone)

        await _push({
            "type": "search_complete",
            "drone_id": drone_id,
            "waypoints_visited": result.waypoints_visited,
            "waypoints_total": result.waypoints_total,
            "survivors_found": len(result.detections),
            "aborted": result.aborted,
            "abort_reason": result.abort_reason,
            "battery_remaining_pct": result.battery_remaining_pct,
        })

    task = asyncio.create_task(run_search())
    _active_searches[drone_id] = task
    return {"started": True, "drone_id": drone_id}


@router.get("/{drone_id}/battery", response_model=BatteryResult)
async def battery(drone_id: str) -> BatteryResult:
    drone = _lookup(drone_id)
    return await get_battery_status(drone)


@router.get("/{drone_id}/status", response_model=StatusResult)
async def status(drone_id: str) -> StatusResult:
    drone = _lookup(drone_id)
    return await get_drone_status(drone)