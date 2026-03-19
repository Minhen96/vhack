from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from drone.api.schemas import DeliverRequest, MoveRequest, ScanRequest, SearchRequest
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


@router.get("/{drone_id}/battery", response_model=BatteryResult)
async def battery(drone_id: str) -> BatteryResult:
    drone = _lookup(drone_id)
    return await get_battery_status(drone)


@router.get("/{drone_id}/status", response_model=StatusResult)
async def status(drone_id: str) -> StatusResult:
    drone = _lookup(drone_id)
    return await get_drone_status(drone)