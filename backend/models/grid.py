from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Terrain(str, Enum):
    OPEN = "OPEN"
    DEBRIS = "DEBRIS"
    RUBBLE = "RUBBLE"
    WATER = "WATER"


@dataclass
class Cell:
    x: int
    y: int

    # ── Terrain ───────────────────────────────────────────────────────────────
    terrain: Terrain = Terrain.OPEN

    # ── Hazards (dynamic — updated each tick) ────────────────────────────────
    fire: bool = False
    fire_intensity: int = 0          # 0–3; higher = faster spread
    fire_age: int = 0                # ticks cell has been on fire
    debris_level: int = 0           # 0–3; affects movement cost and ground height

    # ── Survivor ──────────────────────────────────────────────────────────────
    survivor: bool = False
    survivor_id: str | None = None
    survivor_condition: str = "UNKNOWN"   # STABLE | CRITICAL | UNKNOWN
    time_since_detected: int = 0          # ticks since first scan detection

    # ── Search state ──────────────────────────────────────────────────────────
    searched: bool = False
    search_confidence: float = 0.0        # cumulative scan quality 0–1
    last_scanned_tick: int = -1

    # ── Heatmap ───────────────────────────────────────────────────────────────
    probability: float = 0.0              # likelihood of survivor 0–1

    # ── Navigation (computed) ─────────────────────────────────────────────────
    passable: bool = True

    def compute_risk_level(self) -> int:
        """Returns navigation cost multiplier for pathfinding."""
        if not self.passable:
            return 999
        if self.fire:
            return 8
        if self.terrain == Terrain.RUBBLE:
            return 4
        if self.debris_level >= 2:
            return 3
        if self.debris_level == 1:
            return 2
        return 1

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "terrain": self.terrain.value,
            "fire": self.fire,
            "fire_intensity": self.fire_intensity,
            "debris_level": self.debris_level,
            "survivor": self.survivor,
            "survivor_id": self.survivor_id,
            "survivor_condition": self.survivor_condition,
            "searched": self.searched,
            "search_confidence": round(self.search_confidence, 3),
            "probability": round(self.probability, 3),
            "passable": self.passable,
        }
