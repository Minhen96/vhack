BATTERY_DRAIN_PER_CELL: float = 0.5
BATTERY_DRAIN_SCAN: float = 1.0
BATTERY_DRAIN_DELIVER: float = 1.0
BATTERY_LOW_THRESHOLD: float = 20.0
BATTERY_CRITICAL_THRESHOLD: float = 5.0
BATTERY_CHARGE_RATE: float = 5.0   # % per second while charging at base (100/10 = 10s to full)
SCAN_RADIUS_DEFAULT: int = 8
DRONE_FOV: float = 60.0             # camera field of view in degrees
BASE_X: int = 0
BASE_Y: int = 40  # base station is at the north edge of the map (matches sim server BaseY)
BASE_Z: int = 10  # drone hovers at altitude 10 when idle at base

MAP_X_MIN: int = -40
MAP_X_MAX: int = 40
MAP_Y_MIN: int = -40
MAP_Y_MAX: int = 40