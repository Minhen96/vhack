from pydantic import BaseModel, Field

from drone.constants import SCAN_RADIUS_DEFAULT


class MoveRequest(BaseModel):
    x: int
    y: int
    z: int = 0


class ScanRequest(BaseModel):
    radius: int = Field(default=SCAN_RADIUS_DEFAULT, ge=1, le=50)


class DeliverRequest(BaseModel):
    x: int
    y: int
    z: int = 0


class SearchRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    z: int = 15                                          # search altitude
    step: int = Field(default=10, ge=5, le=30)           # grid spacing between waypoints
    scan_radius: int = Field(default=SCAN_RADIUS_DEFAULT, ge=1, le=50)