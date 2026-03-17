# Rescue Swarm — Autonomous Disaster Rescue System

A simulation of AI-controlled drones that search a disaster area, detect survivors,
coordinate as a swarm, and deliver aid — powered by an LLM agent communicating
purely through MCP tool calls.

**Hackathon Track:** Agentic AI (Decentralised Swarm Intelligence)
**SDGs:** SDG 9 (Innovation & Infrastructure) · SDG 3 (Health & Well-being)

---

## What This Project Does

```
1. A disaster zone (30x30 grid) is generated — fire, debris, survivors scattered around
2. Drones are deployed from a base station
3. An LLM agent (Gemini) observes the map and reasons about what to do
4. The agent sends commands to drones via MCP tool calls (move, scan, deliver)
5. Drones detect survivors, confirm with swarm consensus, then deliver aid
6. Everything streams live to a frontend dashboard
```

---

## Project Structure

```
vhack/
├── backend/                  # Python — simulation engine + API
│   ├── main.py               # FastAPI server, WebSocket, REST endpoints
│   ├── simulation.py         # Core simulation: grid, drones, fire, survivors
│   ├── constants.py          # All config values (grid size, battery rates, etc.)
│   ├── mcp_server.py         # MCP tools the agent uses (Phase B)
│   ├── agent.py              # LLM agent loop (Phase C)
│   ├── models/
│   │   ├── grid.py           # Cell data structure
│   │   ├── drone.py          # Drone data structure
│   │   └── mission.py        # Mission, Survivor, Phase data structures
│   └── utils/
│       ├── pathfinding.py    # A* algorithm — finds best path avoiding fire/debris
│       ├── heatmap.py        # Probability map — where survivors are likely
│       └── mesh.py           # Communication mesh — are drones connected?
├── frontend/                 # Next.js — live dashboard (Phase D)
├── scenarios/
│   └── presets.json          # EARTHQUAKE_ALPHA, TYPHOON_BETA, STRESS_TEST configs
├── TASKS.md                  # Build progress checklist
├── CLAUDE.md                 # Code quality standards
├── plan.md                   # Full architecture plan
├── .env.example              # API key template
└── requirements.txt          # Python dependencies
```

---

## Setup

### 1. Clone and enter project
```bash
cd vhack
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your Gemini API key
```bash
copy .env.example .env
# then open .env and fill in your GOOGLE_API_KEY
```

### 4. Run the backend server
```bash
uvicorn backend.main:app --reload --port 8000
```

You should see:
```
INFO: Scenario 'EARTHQUAKE_ALPHA' loaded. Survivors placed: 5
INFO: Application startup complete.
INFO: Uvicorn running on http://127.0.0.1:8000
```

---

## REST API

With the server running, open your browser or use curl:

| Method | URL | What it returns |
|--------|-----|-----------------|
| GET | `http://localhost:8000/api/map` | Full 30x30 grid with all cell data |
| GET | `http://localhost:8000/api/drones` | All drone positions, battery, status |
| GET | `http://localhost:8000/api/mission` | Phase, coverage %, survivors rescued |
| GET | `http://localhost:8000/api/survivors` | Survivor list with conditions |
| GET | `http://localhost:8000/api/heatmap` | 30x30 probability array |
| POST | `http://localhost:8000/api/mission/start` | Start the simulation |
| POST | `http://localhost:8000/api/mission/pause` | Pause |
| POST | `http://localhost:8000/api/mission/reset` | Reset to fresh map |

### Start a mission (example)
```bash
curl -X POST http://localhost:8000/api/mission/start \
  -H "Content-Type: application/json" \
  -d '{"scenario": "EARTHQUAKE_ALPHA"}'
```

### WebSocket
Connect to `ws://localhost:8000/ws/updates` to receive live events every tick.

---

## How We Tested (Phase A)

We tested each component independently by running Python directly.
No test framework — just direct function calls and print statements to verify behavior.

### Test 1 — Scenario loading
```bash
python -c "
from backend.simulation import Simulation
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
print('Grid:', len(s.grid), 'x', len(s.grid[0]))
print('Drones:', list(s.drones.keys()))
print('Survivors:', len(s.mission.survivors))
"
```
**Expected:** Grid 30x30, 4 drones, 5 survivors

---

### Test 2 — Pathfinding
```bash
python -c "
from backend.simulation import Simulation
from backend.utils.pathfinding import find_path
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
path = find_path(s.grid, (0,0), (5,5))
print('Path length:', len(path))
print('First steps:', path[:3])
"
```
**Expected:** Path of ~10 steps, moving diagonally step by step

---

### Test 3 — Drone movement + battery drain
```bash
python -c "
from backend.simulation import Simulation
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
s.command_move_to('S1', 10, 10)
for i in range(5):
    moved = s._step_drone_positions()
    s._update_battery(moved, set())
    d = s.drones['S1']
    print(f'Tick {i+1}: S1 at ({d.x},{d.y}) battery={d.battery:.1f}')
"
```
**Expected:** Drone moves 1 cell per tick, battery drops 0.8 per move (Scout drain rate)

---

### Test 4 — Thermal scan detects survivor
```bash
python -c "
from backend.simulation import Simulation
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
sv = s.mission.survivors[0]
s.drones['S1'].x = sv.x
s.drones['S1'].y = sv.y
result = s.command_thermal_scan('S1')
print('Detected:', result['detected'])
print('Survivor detected flag:', sv.detected)
"
```
**Expected:** Survivor detected with confidence ~0.7-0.9, `sv.detected = True`

---

### Test 5 — Altitude transitions
```bash
python -c "
from backend.simulation import Simulation
from backend.models.drone import AltitudeState
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
d = s.drones['S1']
d.set_altitude_state(AltitudeState.DELIVERING)
for i in range(12):
    changed = d.step_altitude()
    if changed: print(f'Step {i+1}: altitude={d.altitude}')
print('Final:', d.altitude, '| At target:', d.at_target_altitude)
"
```
**Expected:** Altitude decreases 25→23→21→...→5 over 10 steps, 2 units per step

---

### Test 6 — Aid delivery (altitude gate)
```bash
python -c "
from backend.simulation import Simulation
from backend.models.drone import AltitudeState
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
sv = s.mission.survivors[0]
m1 = s.drones['M1']
m1.x, m1.y = sv.x, sv.y
m1.payload = 'MEDKIT'
print('At altitude 25:', s.command_deliver_aid('M1'))
m1.set_altitude_state(AltitudeState.DELIVERING)
for _ in range(12): m1.step_altitude()
print('At altitude 5:', s.command_deliver_aid('M1'))
print('Rescued:', sv.rescued)
"
```
**Expected:** Fails at altitude 25, succeeds at altitude 5, survivor marked rescued

---

### Test 7 — Fire spread
```bash
python -c "
from backend.simulation import Simulation
s = Simulation()
s.load_scenario('EARTHQUAKE_ALPHA')
before = sum(1 for row in s.grid for c in row if c.fire)
for _ in range(20): s._update_fire()
after = sum(1 for row in s.grid for c in row if c.fire)
print(f'Fire: {before} -> {after} cells after 20 ticks')
"
```
**Expected:** Fire spreads from 3 cells to ~50-70 cells

---

### Test 8 — Full async tick loop
```bash
python -c "
import asyncio
from backend.simulation import Simulation
events = []
async def fake_broadcast(e): events.append(e['event'])
async def run():
    s = Simulation()
    s.set_broadcast(fake_broadcast)
    s.load_scenario('EARTHQUAKE_ALPHA')
    s.command_move_to('S1', 10, 10)
    for _ in range(3): await s._process_tick()
    print('Events fired:', events)
    print('S1 after 3 ticks:', s.drones['S1'].x, s.drones['S1'].y)
asyncio.run(run())
"
```
**Expected:** 3 `tick` events fired, S1 moved 3 cells from base

---

## Build Phases

| Phase | Status | Description |
|-------|--------|-------------|
| A | ✅ Done | Core simulation, models, pathfinding, FastAPI server |
| B | ⬜ Next | MCP server — expose drone tools to agent |
| C | ⬜ | LLM agent — Gemini reasons and calls MCP tools |
| D | ⬜ | Frontend — 2D map, drone list, mission log |
| E | ⬜ | 3D drone view (Three.js) |
| F | ⬜ | Final polish, demo prep |

---

## Key Concepts

### What is a tick?
The simulation runs in discrete time steps called **ticks** (1 per second).
Each tick: drones move one cell, fire may spread, battery drains, events are emitted.

### What is MCP?
Model Context Protocol — a standard way for an LLM to call functions ("tools").
Instead of the agent directly controlling drones, it calls tools like `move_to(drone_id, x, y)`.
This means all decisions are auditable and the agent never hardcodes anything.

### What is the heatmap?
A 30x30 grid of probability values (0.0–1.0) representing how likely each cell
is to contain a survivor. When a drone detects a thermal signal, nearby cells
get boosted. The agent uses this to decide where to search next.

### What is swarm consensus?
Before dispatching a medic, 2 scouts must independently confirm the survivor
(both scan the cell with confidence > 0.7). This prevents false positives.
