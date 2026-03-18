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
    distance = abs(body.x - drone.x) + abs(body.y - drone.y)
    result = await move_to(drone, body.x, body.y, body.z)
    # Notify Map Engine: drone moved to new position and is now idle
    await map_client.send_position(drone, distance)
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/scan", response_model=ScanResult)
async def scan(drone_id: str, body: ScanRequest = ScanRequest()) -> ScanResult:
    drone = _lookup(drone_id)
    result = await thermal_scan(drone, body.radius)
    # Notify Map Engine: each survivor signal found
    for signal in result.survivors:
        await map_client.send_survivor_detected(drone, signal.x, signal.y, drone.z, signal.confidence)
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/deliver", response_model=DeliverResult)
async def deliver(drone_id: str, body: DeliverRequest) -> DeliverResult:
    drone = _lookup(drone_id)
    distance = abs(body.x - drone.x) + abs(body.y - drone.y)
    result = await deliver_aid(drone, body.x, body.y, body.z)
    # Notify Map Engine: aid delivered at location + drone position updated
    if result.status == "delivered":
        await map_client.send_aid_delivered(drone, body.x, body.y, body.z)
    await map_client.send_position(drone, distance)
    await map_client.send_drone_status(drone)
    return result


@router.post("/{drone_id}/return", response_model=ReturnResult)
async def recall(drone_id: str) -> ReturnResult:
    drone = _lookup(drone_id)
    result = await return_to_base(drone)
    # Notify Map Engine: drone is back at base and charging
    await map_client.send_position(drone)
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