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
    status: Literal["arrived", "blocked"]
    position: Position


class ScanResult(BaseModel):
    survivors: list[SurvivorSignal]
    scan_area: ScanArea


class DeliverResult(BaseModel):
    status: Literal["delivered", "failed"]
    location: Position


class BatteryResult(BaseModel):
    drone_id: str
    battery: float
    charging: bool


class StatusResult(BaseModel):
    drone_id: str
    status: str
    position: Position
    battery: float


class ReturnResult(BaseModel):
    status: Literal["returning", "arrived"]
    eta_seconds: int
