from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from drone.api.schemas import DeliverRequest, MoveRequest, ScanRequest
from drone.core.map_client import map_client
from drone.functions import (
    deliver_aid,
    get_battery_status,
    get_drone_status,
    move_to,
    return_to_base,
    thermal_scan,
)
from drone.models.results import (
    BatteryResult,
    DeliverResult,
    MoveResult,
    ReturnResult,
    ScanResult,
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
    # Pushing position here (not at the end) gives map engine a stream of updates
    # so the drone appears to move smoothly across the map in real-time.
    async def on_waypoint(d: Drone, step_dist: int) -> None:
        await map_client.send_position(d, step_dist)
        await map_client.send_drone_status(d)

    result = await move_to(drone, body.x, body.y, body.z, on_waypoint=on_waypoint)
    # Final status push — sets drone to IDLE (or confirms blocked position).
    # Position was already sent at each waypoint above.
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/scan", response_model=ScanResult)
async def scan(drone_id: str, body: ScanRequest = ScanRequest()) -> ScanResult:
    drone = _lookup(drone_id)
    result = await thermal_scan(drone, body.radius)
    # Notify Map Engine: each survivor signal found
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

    # Push live battery updates every second while charging so Map Engine
    # sees the battery rising in real-time without needing to poll
    async def on_tick(d: Drone) -> None:
        await map_client.send_drone_status(d)

    result = await return_to_base(drone, on_waypoint=on_waypoint, on_tick=on_tick)
    # Final status push — charging or blocked
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