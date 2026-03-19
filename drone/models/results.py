from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Position(BaseModel):
    x: int
    y: int
    z: int


class SurvivorSignal(BaseModel):
    x: int
    y: int
    confidence: float


class ScanArea(BaseModel):
    cx: int
    cy: int
    r: int


class MoveResult(BaseModel):
    drone_id: str
    success: bool                          # True = arrived, False = blocked/battery dead
    status: Literal["arrived", "blocked"]
    new_position: Position
    battery_remaining_pct: float


class ScanResult(BaseModel):
    drone_id: str
    scan_position: Position                # where the drone was when it scanned
    survivors_detected: bool               # True if at least one signal found
    detections: list[SurvivorSignal]       # signals above 30°C (likely survivors)
    raw_readings: list[dict]               # all thermal readings unfiltered — for heatmap rendering
    scan_area: ScanArea
    battery_remaining_pct: float


class DeliverResult(BaseModel):
    drone_id: str
    success: bool
    status: Literal["delivered", "failed"]
    delivered_to: Position
    battery_remaining_pct: float
    message: str


class BatteryResult(BaseModel):
    drone_id: str
    battery_pct: float
    charging: bool
    is_low: bool                           # True when battery <= BATTERY_LOW_THRESHOLD
    low_threshold_pct: float               # value of the threshold (default 20%)


class StatusResult(BaseModel):
    drone_id: str
    # MCP-facing status: idle | busy | returning | charging | offline
    # "busy" covers MOVING, SCANNING, DELIVERING internally
    status: str
    current_task: str | None               # detail when status == "busy" (moving/scanning/delivering)
    position: Position
    battery: float


class ReturnResult(BaseModel):
    drone_id: str
    success: bool
    status: Literal["arrived", "blocked"]
    position: Position                     # base position after returning
    battery_pct: float
    message: str
    eta_seconds: int