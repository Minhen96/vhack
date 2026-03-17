# Rescue Swarm — Autonomous Disaster Rescue System

A simulation of AI-controlled drones that search a disaster area, detect survivors,
coordinate as a swarm, and deliver aid — powered by an LLM agent (ARIA) that
reasons autonomously through MCP tool calls.

**Hackathon Track:** Agentic AI (Decentralised Swarm Intelligence)
**SDGs:** SDG 9 (Innovation & Infrastructure) · SDG 3 (Health & Well-being)

---

## How It Works

```
1. A disaster zone (30×30 grid) is generated — fire, debris, survivors scattered around
2. A drone swarm deploys from a base station
3. ARIA (the LLM agent) observes the map and reasons: OBSERVE → ASSESS → DECIDE → EXECUTE
4. ARIA sends commands via MCP tool calls (move, scan, deliver) — never hardcodes drone IDs
5. Scouts detect survivors; swarm consensus (2 confirmations) triggers medic dispatch
6. Everything streams live to a frontend dashboard via WebSocket
```

---

## Project Structure

```
vhack/
├── backend/
│   ├── main.py               # FastAPI app factory + lifespan
│   ├── simulation.py         # Simulation engine: grid, drones, fire, survivors
│   ├── mcp_server.py         # 14 MCP tools (move, scan, rescue, swarm coordination)
│   ├── agent.py              # ARIA — LangGraph ReAct agent loop
│   ├── core/
│   │   ├── config.py         # All constants (grid size, battery rates, altitude, etc.)
│   │   ├── deps.py           # FastAPI dependency injectors (get_sim, get_manager)
│   │   └── websocket.py      # WebSocket connection manager
│   ├── api/
│   │   ├── schemas.py        # Shared response models (CommandResult)
│   │   └── routers/          # One file per resource: map, drones, survivors, mission, ws
│   ├── models/
│   │   ├── grid.py           # Cell dataclass
│   │   ├── drone.py          # Drone dataclass + AltitudeState
│   │   └── mission.py        # Mission, Survivor, Phase models
│   └── utils/
│       ├── pathfinding.py    # A* with risk-weighted costs (fire/debris/water)
│       ├── heatmap.py        # Probability map — survivor likelihood per cell
│       └── mesh.py           # BFS mesh reachability, relay midpoint, mesh health %
├── frontend/                 # Next.js dashboard (Phase D)
├── scenarios/
│   └── presets.json          # EARTHQUAKE_ALPHA, TYPHOON_BETA, STRESS_TEST
├── .env.example              # API key template
└── requirements.txt
```

---

## Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure your LLM provider

```bash
cp .env.example .env
```

Open `.env` and set one provider:

| Provider     | Env key             | Model used         |
| ------------ | ------------------- | ------------------ |
| **Gemini**   | `GOOGLE_API_KEY`    | `gemini-2.0-flash` |
| **DeepSeek** | `DEEPSEEK_API_KEY`  | `deepseek-chat`    |
| **OpenAI**   | `OPENAI_API_KEY`    | `gpt-4o-mini`      |
| **Claude**   | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |

Then set `LLM_PROVIDER=gemini` (or `deepseek` / `openai` / `claude`) in the same `.env`.

### 3. Run the backend
```bash
uvicorn backend.main:app --reload --port 8000
```

Expected output:
```
INFO: Scenario 'EARTHQUAKE_ALPHA' loaded. Survivors placed: 5
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8000
```

---

## REST API

| Method | Endpoint              | Description                                            |
| ------ | --------------------- | ------------------------------------------------------ |
| GET    | `/api/map`            | Full 30×30 grid — terrain, fire, debris, survivor data |
| GET    | `/api/drones`         | All drone positions, battery, status, altitude         |
| GET    | `/api/mission`        | Phase, coverage %, survivors rescued, mesh health      |
| GET    | `/api/survivors`      | Survivor list with conditions and detection state      |
| GET    | `/api/heatmap`        | 30×30 probability array (0.0–1.0)                      |
| POST   | `/api/mission/start`  | Start mission `{"scenario": "EARTHQUAKE_ALPHA"}`       |
| POST   | `/api/mission/pause`  | Pause simulation                                       |
| POST   | `/api/mission/resume` | Resume simulation                                      |
| POST   | `/api/mission/reset`  | Reset to fresh map                                     |

All POST endpoints return a standard `CommandResult`:
```json
{ "success": true, "detail": "Mission started: EARTHQUAKE_ALPHA", "data": null }
```

Errors always return HTTP 4xx/5xx — never a 200 with `{"error": "..."}`.

### WebSocket
```
ws://localhost:8000/ws/updates
```
Receives a full state snapshot on connect (`init` event), then delta updates each tick.

---

## WebSocket Event Types

| Event            | When             | Payload                                           |
| ---------------- | ---------------- | ------------------------------------------------- |
| `init`           | On connect       | Full grid, drones, survivors, mission             |
| `tick`           | Every tick       | Changed cells, moved drones, mission state        |
| `drone_altitude` | Altitude changes | `drone_id`, `altitude`, `state`                   |
| `survivor_found` | Detection        | `x`, `y`, `condition`                             |
| `aid_delivered`  | Rescue complete  | `survivor_id`, `drone_id`                         |
| `fire_spread`    | Fire spreads     | `new_fire_cells`                                  |
| `aftershock`     | Every ~120 ticks | `affected_cells`                                  |
| `phase_change`   | Phase transition | `from`, `to`, `tick`                              |
| `leader_changed` | Leader election  | `old`, `new`                                      |
| `agent_thought`  | ARIA reasoning   | `phase` (OBSERVE/THINKING/EXECUTE/RESULT), `text` |

---

## Smoke Tests

```bash
# Scenario loading
python -c "
from backend.simulation import Simulation
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
print('Grid:', len(s.grid), 'x', len(s.grid[0]))
print('Drones:', list(s.drones.keys()))
print('Survivors:', len(s.mission.survivors))
"
# Expected: Grid 30x30, drones ['S1','S2','M1','R1'], survivors 5

# Pathfinding
python -c "
from backend.simulation import Simulation
from backend.utils.pathfinding import find_path
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
path = find_path(s.grid, (0,0), (5,5))
print('Path length:', len(path), '| First steps:', path[:3])
"
# Expected: ~10 steps

# Altitude gate — deliver_aid only works at altitude ≤ 8
python -c "
from backend.simulation import Simulation
from backend.models.drone import AltitudeState
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
sv = s.mission.survivors[0]
m1 = s.drones['M1']
m1.x, m1.y = sv.x, sv.y
m1.payload = 'MEDKIT'
print('At altitude 25:', s.command_deliver_aid('M1')['success'])   # False
m1.set_altitude_state(AltitudeState.DELIVERING)
for _ in range(12): m1.step_altitude()
print('At altitude 5:', s.command_deliver_aid('M1')['success'])    # True
"

# Full async tick loop
python -c "
import asyncio
from backend.simulation import Simulation
async def run():
    async def noop(e): pass
    s = Simulation()
    s.set_broadcast(noop)
    s.load_scenario('EARTHQUAKE_ALPHA')
    s.command_move_to('S1', 10, 10)
    for _ in range(3): await s._process_tick()
    print('S1 after 3 ticks:', s.drones['S1'].x, s.drones['S1'].y)
asyncio.run(run())
"
# Expected: S1 moved 3 cells toward (10,10)
```

---

## Build Phases

| Phase | Status | Description                                                      |
| ----- | ------ | ---------------------------------------------------------------- |
| A     | ✅ Done | Simulation engine, models, pathfinding, FastAPI + WebSocket      |
| B     | ✅ Done | MCP server — 14 drone tools exposed via FastMCP                  |
| C     | ✅ Done | ARIA agent — LangGraph ReAct loop, provider switch, WS streaming |
| D     | 🔲 Next | Frontend — 2D map, drone list, mission log                       |
| E     | 🔲      | 3D drone view (React Three Fiber)                                |
| F     | 🔲      | Final polish, demo prep                                          |

---

## Key Concepts

**Tick** — The simulation advances in discrete 1-second steps. Each tick: drones move one cell, fire may spread, battery drains, WebSocket delta is broadcast.

**MCP** — Model Context Protocol. ARIA never calls simulation functions directly — it calls tools like `move_to(drone_id, x, y)`. Every drone action is auditable.

**Heatmap** — A 30×30 probability grid (0.0–1.0). Thermal scans boost probability at detected cells. The agent uses this to decide where to search next.

**Swarm consensus** — Before dispatching a medic, 2 scouts must independently confirm a survivor via `deep_scan()` (confidence > 0.7 each). Prevents false positives.

**Altitude states** — Drone altitude is a real simulation field, not a visual trick. `DELIVERING (5)` is required for `deliver_aid()` to succeed. `SCANNING (15)` applies a +0.15 confidence bonus.

**Leader election** — The drone with highest battery + best position leads the swarm. If the leader's battery drops below 30% or it goes offline, the next eligible drone takes over and ARIA is notified to replan.
