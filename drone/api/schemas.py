from pydantic import BaseModel, Field

from drone.constants import SCAN_RADIUS_DEFAULT


class MoveRequest(BaseModel):
    x: int
    y: int
    z: int = 0


class ScanRequest(BaseModel):
    radius: int = Field(default=SCAN_RADIUS_DEFAULT, ge=1, le=10)


class DeliverRequest(BaseModel):
    x: int
    y: int
    z: int = 0