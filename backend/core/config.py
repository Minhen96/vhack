import os
from dotenv import load_dotenv

load_dotenv()

# ── Grid ──────────────────────────────────────────────────────────────────────
GRID_SIZE: int = int(os.getenv("GRID_SIZE", "30"))
CELL_SIZE_METERS: int = 5  # real-world equivalent per cell

# ── Simulation ────────────────────────────────────────────────────────────────
TICK_RATE: float = float(os.getenv("TICK_RATE", "1.0"))  # ticks per second

# ── Base Station ──────────────────────────────────────────────────────────────
BASE_X: int = GRID_SIZE // 2
BASE_Y: int = GRID_SIZE - 1
BASE_COMM_RANGE: int = 10

# ── Drone Altitude (world units) ──────────────────────────────────────────────
ALTITUDE_CRUISING: int = 25
ALTITUDE_SCANNING: int = 15
ALTITUDE_DELIVERING: int = 5
ALTITUDE_RETURNING: int = 20
ALTITUDE_TRANSITION_SPEED: int = 2  # units moved per tick toward target

# ── Battery ───────────────────────────────────────────────────────────────────
# Drain per cell moved, per role
BATTERY_DRAIN: dict[str, float] = {
    "SCOUT": 0.8,
    "MEDIC": 1.2,
    "RELAY": 0.1,
    "HEAVY": 2.0,
}
BATTERY_RETURN_BUFFER: float = 1.3   # 30 % safety margin before returning
BATTERY_CHARGE_RATE: float = 5.0     # % per tick while at base

# ── Communication Range (cells) ───────────────────────────────────────────────
COMM_RANGE: dict[str, int] = {
    "SCOUT": 10,
    "MEDIC": 10,
    "RELAY": 20,
    "HEAVY": 8,
}

# ── Scan ──────────────────────────────────────────────────────────────────────
SCAN_RADIUS: dict[str, int] = {
    "SCOUT": 2,
    "MEDIC": 1,
    "RELAY": 0,
    "HEAVY": 1,
}
SCAN_BASE_ACCURACY: dict[str, float] = {
    "SCOUT": 0.85,
    "MEDIC": 0.60,
    "RELAY": 0.0,
    "HEAVY": 0.60,
}
SCAN_ALTITUDE_BONUS: float = 0.15    # added when altitude_state == SCANNING

# ── A* Pathfinding ────────────────────────────────────────────────────────────
RISK_DEBRIS_PER_LEVEL: float = 2.0
RISK_FIRE_PENALTY: float = 50.0
RISK_WATER_PENALTY: float = 999.0
RISK_DRONE_SOFT_PENALTY: float = 1.0

# ── Fire Dynamics ─────────────────────────────────────────────────────────────
FIRE_SPREAD_CHANCE: float = 0.08     # per adjacent passable cell per tick
FIRE_BURNOUT_TICKS: int = 20         # ticks before burnout becomes possible
FIRE_BURNOUT_CHANCE: float = 0.15   # chance per tick once eligible

# ── Survivor ──────────────────────────────────────────────────────────────────
SURVIVOR_DETERIORATION_TICKS: int = 60   # STABLE → CRITICAL

# ── Aftershock ────────────────────────────────────────────────────────────────
AFTERSHOCK_INTERVAL: int = 120       # ticks between events
AFTERSHOCK_CELLS: int = 6            # cells affected per aftershock

# ── Heatmap ───────────────────────────────────────────────────────────────────
HEATMAP_DECAY_RATE: float = 0.97
HEATMAP_DETECT_BOOST: float = 0.5
HEATMAP_NEIGHBOR_BOOST: float = 0.3

# ── Probability Thresholds ────────────────────────────────────────────────────
PROB_CONVERGENCE: float = 0.60       # phase SEARCH → CONVERGENCE
PROB_CONFIRMATION: float = 0.85      # triggers swarm consensus request
MEDIC_CONFIDENCE_THRESHOLD: float = 0.70   # min confidence to dispatch medic

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
