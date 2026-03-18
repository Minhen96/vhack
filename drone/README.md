# Drone Service

One process = one drone. Each drone instance is a FastAPI server that:
- Exposes HTTP endpoints for the MCP server to call
- Pushes real-time state to the Map Engine over WebSocket
- Receives live obstacle data from the Map Engine to navigate autonomously

---

## Architecture

```
LLM
 │  decides where to go, what to scan, when to deliver
 ▼
MCP Server                        ← drone registers capabilities here on startup
 │  HTTP tool calls for drone ops
 │  (list/backup handled by MCP itself — no drone call needed)
 ▼
Drone Service (this)
 │  ↑  WebSocket — bidirectional
 │  └─ Drone → Map: position, camera direction (every step)
 │  └─ Map → Drone: obstacle grid (on connect + real-time updates)
 ▼
Map Engine
```

**Who handles each MCP tool:**

| MCP Tool | Handled by |
|---|---|
| `move_to` | MCP → `POST /drones/{id}/move` |
| `thermal_scan` | MCP → `POST /drones/{id}/scan` |
| `deliver_aid` | MCP → `POST /drones/{id}/deliver` |
| `return_to_base` | MCP → `POST /drones/{id}/return` |
| `get_battery_status` | MCP → `GET /drones/{id}/battery` |
| `get_drone_status` | MCP → `GET /drones/{id}/status` |
| `get_drone_capabilities` | MCP only — reads from its own registration record |
| `list_active_drones` | MCP only — aggregates all registered drones |
| `request_backup` | MCP only — orchestrates two drones using existing tools |

**Movement flow:**
1. LLM decides where to go → MCP calls `POST /drones/{id}/move`
2. Drone looks up latest obstacle cache (from Map Engine WS, zero extra I/O)
3. A* plans a path around blocked cells
4. Drone walks step-by-step — before **every single cell**, re-runs A* with the freshest obstacle data (never commits to a full path upfront)
5. After each step: sends updated position + camera direction to Map Engine
6. Map Engine sends back any grid changes that happened mid-path (new rubble, other drones moving)
7. Drone re-routes on the fly if the path changed
8. LLM gets back `"arrived"` or `"blocked"` — it never thinks about obstacles

**Return to base flow:**
1. LLM calls `POST /drones/{id}/return`
2. Drone navigates home via A* (same obstacle avoidance as move)
3. On arrival, starts gradual charge at `BATTERY_CHARGE_RATE`%/s (configurable in `constants.py`)
4. Map Engine receives a `send_drone_status` update every second showing battery rising
5. LLM gets back `"arrived"` with `eta_seconds` (manhattan estimate) and current `battery_pct`

**WebSocket reconnect:**
- If Map Engine goes down, drone retries connection every 5 seconds automatically
- On reconnect, re-sends `init_connection` so Map Engine knows the drone is back

**WebSocket send safety:**
- All outbound messages go through an `asyncio.Queue` (capped at 256 entries)
- A single `_write_pump` background task drains the queue and sends messages one at a time
- This prevents payload corruption from concurrent sends on the same socket
- If the queue is full (map engine unreachable), the oldest message is dropped to make room for the latest

---

## Endpoints

All endpoints are prefixed with `/drones/{drone_id}`.

| Method | Path                  | Description                               |
| ------ | --------------------- | ----------------------------------------- |
| POST   | `/{drone_id}/move`    | Move to (x, y, z) — A* obstacle avoidance |
| POST   | `/{drone_id}/scan`    | Thermal scan at current position          |
| POST   | `/{drone_id}/deliver` | Deliver aid to (x, y, z)                  |
| POST   | `/{drone_id}/return`  | Return to base and recharge               |
| GET    | `/{drone_id}/battery` | Get battery level                         |
| GET    | `/{drone_id}/status`  | Get full drone status                     |

Interactive docs available at `http://localhost:{DRONE_PORT}/docs` when running.

---

## WebSocket Contract with Map Engine

### Drone → Map Engine (outbound)

| `intention`         | When                      | Key fields                           |
| ------------------- | ------------------------- | ------------------------------------ |
| `init_connection`   | On startup                | `type`, `capabilities`, `position`   |
| `send_position`     | After every movement step | `x`, `y`, `z`, `spherical`, `eta_ms` |
| `send_drone_status` | After any state change    | `status`, `battery`                  |
| `survivor_detected` | After scan finds a signal | `x`, `y`, `z`, `confidence`          |
| `aid_delivered`     | After successful delivery | `x`, `y`, `z`                        |

`spherical` contains `azimuth`, `elevation`, `scan_radius`, `fov` for Map Engine's 3D camera view.
`azimuth` uses compass convention: 0 = North, 90 = East, clockwise.
`eta_ms` = step distance × 200ms — tells Map Engine how long to lerp the drone position for smooth animation.

### Map Engine → Drone (inbound)

| `intention`     | When                    | Key fields                                     |
| --------------- | ----------------------- | ---------------------------------------------- |
| `grid_snapshot` | Once on drone connect   | `blocked: [[x,y], ...]` — full obstacle map    |
| `grid_update`   | Whenever a cell changes | `x`, `y`, `passable: bool` — single cell patch |

The drone keeps a live `_blocked` cache from these messages. A* re-reads it before every cell move, so the drone reacts to obstacles discovered mid-path (rubble found by scan, another drone entering a cell, etc.).

---

## Drone Types & Capabilities

All drones share a set of common capabilities regardless of type.
Type-specific capabilities define what makes each type unique.

**Common (all types):** `move_to`, `return_to_base`, `get_battery_status`, `get_drone_status`

| Type       | Type-specific capability |
| ---------- | ------------------------ |
| `scanner`  | `thermal_scan`           |
| `delivery` | `deliver_aid`            |

The full capability list (common + type-specific) is sent to MCP and Map Engine on startup so they know what each drone can do.

---

## Setup

```bash
cd drone
cp .env.example .env
# Edit .env — set DRONE_TYPE, DRONE_PORT, MCP_URL, MAP_WS_URL

pip install fastapi uvicorn websockets httpx python-dotenv
uvicorn drone.main:app --host 0.0.0.0 --port 8001
```

To run multiple drones, copy `.env` with a different `DRONE_PORT` and `DRONE_TYPE`, then start another process. Each instance auto-generates a unique `DRONE_ID` (`{type}_{port}_{random4}`).

---

## Environment Variables

| Variable     | Default                        | Description                                            |
| ------------ | ------------------------------ | ------------------------------------------------------ |
| `DRONE_ID`   | auto                           | Leave blank — auto-generated as `{type}_{port}_{rand}` |
| `DRONE_TYPE` | `scanner`                      | `scanner` \| `delivery`                                |
| `DRONE_HOST` | `localhost`                    | Host reported to MCP on registration                   |
| `DRONE_PORT` | `8001`                         | Port this process listens on                           |
| `MCP_URL`    | `http://localhost:9000`        | MCP server base URL                                    |
| `MAP_WS_URL` | `ws://localhost:9001/ws/drone` | Map Engine WebSocket URL                               |

---

## Project Structure

```
drone/
├── main.py               # FastAPI app, lifespan (startup/shutdown)
├── functions.py          # Core drone logic (move_to, scan, deliver, ...)
├── pathfinding.py        # A* pathfinding — finds shortest path avoiding blocked cells
├── registry.py           # Single drone instance per process
├── constants.py          # All tuneable numbers in one place
├── models/
│   ├── drone.py          # Drone dataclass, DroneType, DroneStatus, CAPABILITIES, COMMON_CAPABILITIES
│   └── results.py        # Pydantic response models
├── api/
│   ├── schemas.py        # Request body models
│   └── routers/
│       └── drones.py     # HTTP route handlers
└── core/
    ├── config.py         # Env var loading, DRONE_ID generation
    ├── map_client.py     # WebSocket client to Map Engine (send + receive)
    └── registration.py   # MCP register/deregister (HTTP)
```