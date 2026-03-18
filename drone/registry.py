from __future__ import annotations

from drone.models.drone import Drone

# The single drone instance for this process.
# A dict is used as a mutable container to avoid the `global` keyword.
_state: dict[str, Drone | None] = {"drone": None}


def set_drone(drone: Drone) -> None:
    _state["drone"] = drone


def get_drone() -> Drone | None:
    return _state["drone"]