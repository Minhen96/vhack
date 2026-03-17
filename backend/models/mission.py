from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MissionPhase(str, Enum):
    IDLE = "IDLE"
    DEPLOYMENT = "DEPLOYMENT"
    SEARCH = "SEARCH"
    CONVERGENCE = "CONVERGENCE"
    CONFIRMATION = "CONFIRMATION"
    RESCUE = "RESCUE"
    EXTRACT = "EXTRACT"
    COMPLETE = "COMPLETE"


class SurvivorCondition(str, Enum):
    STABLE = "STABLE"
    CRITICAL = "CRITICAL"
    RESCUED = "RESCUED"
    UNKNOWN = "UNKNOWN"


class ScenarioKey(str, Enum):
    EARTHQUAKE_ALPHA = "EARTHQUAKE_ALPHA"
    TYPHOON_BETA = "TYPHOON_BETA"
    STRESS_TEST = "STRESS_TEST"


@dataclass
class Survivor:
    id: str
    x: int
    y: int
    condition: SurvivorCondition = SurvivorCondition.STABLE
    detected: bool = False
    rescued: bool = False
    detected_tick: int = -1
    rescued_tick: int = -1
    time_since_detected: int = 0
    confirmed_by: list[str] = field(default_factory=list)   # drone IDs that confirmed

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "condition": self.condition.value,
            "detected": self.detected,
            "rescued": self.rescued,
            "detected_tick": self.detected_tick,
            "rescued_tick": self.rescued_tick,
            "confirmed_by": self.confirmed_by,
        }


@dataclass
class Mission:
    scenario: ScenarioKey = ScenarioKey.EARTHQUAKE_ALPHA
    phase: MissionPhase = MissionPhase.IDLE
    tick: int = 0
    active: bool = False
    paused: bool = False

    survivors: list[Survivor] = field(default_factory=list)

    # ── Coverage tracking ─────────────────────────────────────────────────────
    total_cells: int = 0
    searched_cells: int = 0

    # ── Aftershock tracking ───────────────────────────────────────────────────
    last_aftershock_tick: int = 0

    @property
    def coverage_percent(self) -> float:
        if self.total_cells == 0:
            return 0.0
        return round((self.searched_cells / self.total_cells) * 100, 1)

    @property
    def survivors_rescued(self) -> int:
        return sum(1 for s in self.survivors if s.rescued)

    @property
    def survivors_detected(self) -> int:
        return sum(1 for s in self.survivors if s.detected)

    @property
    def survivors_total(self) -> int:
        return len(self.survivors)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario.value,
            "phase": self.phase.value,
            "tick": self.tick,
            "active": self.active,
            "paused": self.paused,
            "coverage_percent": self.coverage_percent,
            "survivors_total": self.survivors_total,
            "survivors_detected": self.survivors_detected,
            "survivors_rescued": self.survivors_rescued,
        }
