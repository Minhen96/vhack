import os
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

MCP_URL = os.getenv("MCP_URL", "http://localhost:8000")
MAP_WS_URL = os.getenv("MAP_WS_URL", "ws://localhost:8080/ws/drone")

DRONE_HOST = os.getenv("DRONE_HOST", "localhost")
DRONE_PORT = int(os.getenv("DRONE_PORT", "8001"))
DRONE_TYPE = os.getenv("DRONE_TYPE", "scanner")

SIM_SERVER_URL = os.getenv("SIM_SERVER_URL", "http://localhost:8080")

# If DRONE_ID is not set explicitly, derive from type + port + random 4-char suffix
# so each process is guaranteed unique even if type and port collide (scanner_8001_a3f2).
DRONE_ID = os.getenv("DRONE_ID") or f"{DRONE_TYPE}_{DRONE_PORT}_{uuid.uuid4().hex[:4]}"