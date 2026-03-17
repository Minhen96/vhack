# Hackathon Plan — Autonomous Disaster Rescue Swarm
**Track:** Agentic AI (Decentralised Swarm Intelligence)
**SDGs:** SDG 9 (9.1, 9.5) · SDG 3 (3.d)

---

## 0. Core Concept & Differentiators

> ASEAN disaster zones lose cloud + cell tower access within hours of impact.
> This system simulates autonomous rescue coordination using an LLM agent
> that operates purely through MCP tool calls — no hardcoded decisions,
> no human pilots, full chain-of-thought reasoning visible in real-time.

**What makes this stand out:**
- LLM agent reasons and plans autonomously via MCP (Gemini / DeepSeek / OpenAI)
- Swarm consensus before medic dispatch (avoids false positives)
- Dynamic environment: fire spreads, debris shifts each tick
- Drone leader election — if lead drone loses battery, another takes over
- Multi-hop relay mesh routing (not just single relay)
- Survivor triage system — priority queue based on signal strength + time elapsed
- Mission phases with automatic phase transitions
- Live agent chain-of-thought streamed to frontend

---

## 1. Overall System Architecture

```
Operator / Browser
        │
        ▼
┌─────────────────────────────┐
│   Frontend (Next.js 14)     │  ← 2D Command Map + 3D Drone View
│   Tailwind + Three.js       │    + Mission Log + Metrics Dashboard
└────────────┬────────────────┘
             │  WebSocket (ws://) + REST
             ▼
┌─────────────────────────────┐
│   Backend (FastAPI)         │  ← Simulation tick engine
│   Python 3.11               │    Real-time event bus
│   Uvicorn + asyncio         │    State manager
└──────┬──────────┬───────────┘
       │          │
       ▼          ▼
┌──────────┐  ┌──────────────────────────────┐
│ Simulation│  │  LLM Command Agent           │
│  Engine  │  │  (LangChain + Gemini /        │
│ (custom  │  │   DeepSeek / OpenAI)          │
│  grid)   │  │  Chain-of-Thought reasoning   │
└──────────┘  └──────────────┬───────────────┘
                             │  MCP tool calls
                             ▼
                ┌────────────────────────┐
                │   MCP Server           │
                │   (FastMCP / Python)   │
                │   Drone Tool Registry  │
                └────────────────────────┘
```

**Design note:** Simulation + MCP + WebSocket all run locally on a single laptop.
Only the LLM reasoning step calls an external API (Gemini/DeepSeek).

**Async decoupling — critical:** The simulation tick loop and agent loop run as
separate `asyncio` tasks so a slow LLM response never freezes the simulation:
```python
@app.on_event("startup")
async def startup():
    asyncio.create_task(simulation_tick_loop())   # ticks every 1s regardless
    asyncio.create_task(agent_loop())             # waits for LLM, non-blocking
```

---

## 2. Disaster Environment — Grid Simulation

### Grid Specification
- **Size:** 30×30 cells (adjustable via config)
- **Cell = 5×5 meters** real-world equivalent
- **Tick rate:** 1 tick/second (configurable)

### Cell Data Model
```python
@dataclass
class Cell:
    x: int
    y: int
    # Terrain
    terrain: Terrain          # OPEN | DEBRIS | RUBBLE | WATER
    # Hazards (dynamic — change each tick)
    fire: bool
    fire_intensity: int       # 0–3, affects spread probability
    debris_level: int         # 0–3, affects movement cost
    # Survivor
    survivor: bool
    survivor_id: str | None
    survivor_condition: str   # STABLE | CRITICAL | UNKNOWN
    time_since_detected: int  # ticks since first detection
    # Search state
    searched: bool
    search_confidence: float  # 0–1, cumulative scan quality
    last_scanned_tick: int
    # Probability heatmap
    probability: float        # 0–1 likelihood of survivor
    # Navigation
    risk_level: int           # computed: 1=open, 3=debris, 8=fire
    passable: bool
```

### Dynamic Environment Events (each tick)
| Event | Logic | Effect |
|---|---|---|
| Fire spread | Each fire cell has 8% chance to spread to adjacent open cell | `fire=True, risk+=5` |
| Fire burnout | Fire lasting >20 ticks has 15% chance to self-extinguish | `fire=False` |
| Debris shift | Low probability random debris appears / clears | `terrain changes` |
| Survivor deterioration | `STABLE → CRITICAL` after 60 ticks unrescued | Priority escalates |
| Aftershock | Every ~120 ticks, random debris expansion event | Multiple cells affected |

### Initial Map Generation
- Seeded random generation with configurable disaster profile:
  - `EARTHQUAKE` — dense debris, few fires, survivors in rubble
  - `TYPHOON` — flooded zones (impassable water), scattered debris
  - `FIRE_DISASTER` — large fire zones, survivors at perimeter
- Survivors placed using Gaussian clusters (more realistic than uniform random)

---

## 3. Drone Simulation

### Drone Data Model
```python
@dataclass
class Drone:
    id: str                   # e.g. "DRONE-A1"
    role: DroneRole           # SCOUT | MEDIC | RELAY | HEAVY
    x: int
    y: int
    battery: int              # 0–100
    battery_drain_rate: float # per cell moved (role-dependent)
    status: DroneStatus       # IDLE | SCANNING | MOVING | DELIVERING
                              # RETURNING | CHARGING | OFFLINE
    payload: str | None       # "MEDKIT" | "FOOD" | None
    communication_range: int  # cells
    scan_radius: int          # cells
    scan_accuracy: float      # 0–1 (degrades in fire/debris zones)
    path: list[tuple]         # current planned path
    target: tuple | None      # destination cell
    mission_id: str | None    # assigned mission task
    leader: bool              # is this drone the swarm leader?
    last_seen_tick: int       # for relay mesh staleness detection
    # Altitude (real simulation data — not just visual)
    altitude: int             # actual tracked value, see AltitudeState
    altitude_state: str       # CRUISING | SCANNING | DELIVERING | RETURNING
```

### Drone Altitude States
Altitude is a **real simulation field** — not a visual trick. It has 4 states with
actual meaning that the agent can reason about and the 3D view reflects directly:

```python
class AltitudeState:
    CRUISING   = 25   # moving between cells, full speed
    SCANNING   = 15   # descends to improve scan accuracy (+0.15 confidence bonus)
    DELIVERING =  5   # descends close to ground to drop aid
    RETURNING  = 20   # slightly lower altitude, conservative flight home

# Altitude transition logic (simulation.py)
def update_drone_altitude(drone):
    target = AltitudeState[drone.altitude_state]
    # smooth transition: move 2 units per tick toward target
    if drone.altitude < target:
        drone.altitude = min(drone.altitude + 2, target)
    elif drone.altitude > target:
        drone.altitude = max(drone.altitude - 2, target)
```

**Why this matters:**
- `SCANNING` at altitude 15 gives real +0.15 scan confidence bonus in simulation
- `DELIVERING` at altitude 5 is required for `deliver_aid()` to succeed
- Agent logs e.g. `"Descending DRONE-M1 to altitude 5 for aid delivery"` — visible in mission log
- 3D view reads `drone.altitude` directly — no faking needed

### Drone Roles & Capabilities
| Role | Speed | Battery Drain | Special Ability | Payload |
|---|---|---|---|---|
| Scout | Fast (1 cell/tick) | 0.8/move | Thermal scan radius 2 | None |
| Medic | Medium (0.7/tick) | 1.2/move | Can deliver aid | Medkit / Food |
| Relay | Stationary/slow | 0.1/tick | Extends mesh range ×2 | None |
| Heavy | Slow (0.5/tick) | 2.0/move | Carries multiple kits, clears light debris | 3× Medkits |

### Pathfinding
- **Algorithm:** A* with weighted cost function:
  ```
  cost(cell) = base_cost
             + (debris_level × 2)
             + (fire ? 50 : 0)         ← hard avoidance
             + (water ? 999 : 0)       ← impassable
             + (other_drone_nearby ? 1 : 0)  ← soft collision avoidance
  ```
- Paths are recalculated every 5 ticks or when environment changes significantly
- **Cooperative pathfinding:** Drones reserve cells for 1 tick to avoid collisions

### Battery Management
```
critical_distance = distance_to_base(drone)
battery_needed_to_return = critical_distance × drain_rate × 1.3  ← 30% safety buffer
should_return = drone.battery <= battery_needed_to_return
```
- Drones proactively plan return before battery critical
- Medic drones prioritize survivor delivery over charging

### Leader Election
- On mission start, drone with highest battery + best position = leader
- Leader broadcasts grid assignments to other drones (via simulated mesh)
- If leader battery < 30% OR leader goes offline:
  → Next eligible drone (highest score) becomes leader
  → Agent is notified and updates its plan

---

## 4. MCP Server — Standardized Drone API

### Tool Registry (FastMCP)

```python
# ── Discovery ──────────────────────────────────────────────
@mcp.tool()
def list_active_drones() -> list[DroneInfo]:
    """Returns all drones currently online with role, battery, position."""

@mcp.tool()
def get_drone_status(drone_id: str) -> DroneStatus:
    """Full status of a specific drone."""

# ── Movement ───────────────────────────────────────────────
@mcp.tool()
def move_to(drone_id: str, x: int, y: int) -> MoveResult:
    """Move drone to cell. Returns path cost and ETA in ticks."""

@mcp.tool()
def assign_sector(drone_id: str, sector: str) -> SectorAssignment:
    """Assign drone to a named quadrant (NW/NE/SW/SE). Auto-plans coverage."""

# ── Sensing ────────────────────────────────────────────────
@mcp.tool()
def thermal_scan(drone_id: str) -> ScanResult:
    """Scan surrounding cells. Returns {cell: confidence} dict."""

@mcp.tool()
def deep_scan(drone_id: str, x: int, y: int) -> DeepScanResult:
    """Focused scan on specific cell. Higher confidence, uses extra battery."""

# ── Resource Management ────────────────────────────────────
@mcp.tool()
def get_battery_status(drone_id: str) -> int:
    """Returns battery percentage."""

@mcp.tool()
def return_to_base(drone_id: str) -> ReturnResult:
    """Recall drone. Returns ETA."""

@mcp.tool()
def deploy_relay(x: int, y: int) -> RelayResult:
    """Station a relay drone at position to extend mesh range."""

# ── Rescue ─────────────────────────────────────────────────
@mcp.tool()
def dispatch_medic(drone_id: str, target_x: int, target_y: int) -> DispatchResult:
    """Send medic drone to confirmed survivor. Returns success/failure."""

@mcp.tool()
def deliver_aid(drone_id: str) -> DeliveryResult:
    """Execute aid delivery at current drone position."""

# ── Environment ────────────────────────────────────────────
@mcp.tool()
def get_map_state() -> GridState:
    """Full grid snapshot: cells, drones, survivors, fire zones."""

@mcp.tool()
def get_heatmap() -> list[list[float]]:
    """Returns 2D probability array for survivor likelihood."""

@mcp.tool()
def get_mission_status() -> MissionStatus:
    """Returns phase, survivors found/rescued, coverage %, elapsed ticks."""

# ── Swarm Coordination ─────────────────────────────────────
@mcp.tool()
def broadcast_finding(drone_id: str, x: int, y: int, confidence: float) -> None:
    """Share discovery with swarm. Updates shared heatmap."""

@mcp.tool()
def request_confirmation(x: int, y: int) -> ConfirmationRequest:
    """Request another drone to confirm a survivor detection."""
```

### MCP Rules
- Agent **never** hardcodes drone IDs — always calls `list_active_drones()` first
- Agent must call `get_mission_status()` at the start of each reasoning cycle
- All tool calls logged to mission log with timestamp + agent reasoning

---

## 5. LLM Command Agent

### Agent Architecture
```
┌─────────────────────────────────────────────────────┐
│                  Command Agent Loop                  │
│                                                      │
│  1. OBSERVE   → get_map_state() + get_mission_status()
│  2. REFLECT   → Analyze: coverage gaps, battery,    │
│                 unconfirmed signals, active threats  │
│  3. PRIORITIZE→ Build priority queue:               │
│                 CRITICAL survivors > STABLE >        │
│                 unscanned high-prob > low-prob       │
│  4. PLAN      → Assign drones to tasks (no overlap) │
│  5. ACT       → Execute MCP tool calls              │
│  6. LEARN     → Update internal memory (discoveries,│
│                 failed paths, confirmed clears)      │
│  7. LOG       → Emit chain-of-thought to frontend   │
│  8. SLEEP(1s) → Wait for next tick                  │
└─────────────────────────────────────────────────────┘
```

### LLM Configuration

Pick **any one** provider — just set the API key in `.env`:

| Provider | Model | LangChain class | `.env` key |
|---|---|---|---|
| **Google Gemini** ✅ recommended | `gemini-2.0-flash` | `ChatGoogleGenerativeAI` | `GOOGLE_API_KEY` |
| **DeepSeek** ✅ cheap | `deepseek-chat` | `ChatOpenAI` (OpenAI-compat.) | `DEEPSEEK_API_KEY` |
| **OpenAI** | `gpt-4o-mini` | `ChatOpenAI` | `OPENAI_API_KEY` |
| **Anthropic** | `claude-haiku-4-5` | `ChatAnthropic` | `ANTHROPIC_API_KEY` |

```python
# agent.py — swap provider by changing one import
import os
from langchain_google_genai import ChatGoogleGenerativeAI   # Gemini
# from langchain_openai import ChatOpenAI                   # OpenAI or DeepSeek
# from langchain_anthropic import ChatAnthropic             # Claude

def build_llm():
    provider = os.getenv("LLM_PROVIDER", "gemini")  # set in .env
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.3,
        )
    elif provider == "deepseek":
        return ChatOpenAI(
            model="deepseek-chat",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0.3,
        )
    elif provider == "openai":
        return ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    elif provider == "claude":
        return ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0.3)
```

- **Framework:** LangChain with MCP adapters (`langchain-mcp-adapters`)
- **Prompt strategy:** System prompt defines agent persona + mission rules + output format
- **Recommended for hackathon:** Gemini Flash (generous free tier) or DeepSeek (very cheap)

### System Prompt (core excerpt)
```
You are ARIA (Autonomous Rescue Intelligence Agent), coordinating a drone swarm
in a post-disaster zone with NO cloud connectivity.

Your constraints:
- Always check battery before assigning long missions
- Never send a Medic unless at least 2 Scout scans confirm survivor (confidence > 0.7)
- Maintain at least 1 relay drone deployed if any scout is >8 cells from base
- Prioritize CRITICAL condition survivors over STABLE
- If a cell has been scanned with >0.9 confidence and no survivor found, mark clear

Your chain-of-thought format:
OBSERVE: [current state summary]
ASSESS: [risks, opportunities, bottlenecks]
DECIDE: [ranked action list with reasoning]
EXECUTE: [MCP tool calls]
```

### Swarm Consensus Protocol
Before dispatching a Medic drone:
1. First Scout detects thermal signal → `broadcast_finding()`
2. Agent calls `request_confirmation()` → second Scout sent
3. Second Scout confirms (confidence > 0.7) → Medic dispatched
4. If contradiction (one confirms, one denies) → agent sends third Scout
- This prevents false positives and wasted Medic trips

### Agent Memory (in-context, per session)
```python
agent_memory = {
    "cleared_cells": set(),         # confirmed no survivor
    "confirmed_survivors": list(),  # waiting for medic
    "rescued_survivors": list(),    # completed
    "failed_paths": list(),         # cells that blocked pathing
    "relay_positions": list(),      # currently deployed relays
    "last_aftershock_tick": int,    # to re-evaluate paths after events
}
```

---

## 6. Adaptive Search — Enhanced Heatmap

### Probability Update Rules
```python
# On thermal scan detection
def update_heatmap(x, y, confidence):
    grid[x][y].probability = min(1.0, grid[x][y].probability + 0.5 * confidence)
    for nx, ny in get_neighbors(x, y, radius=2):
        dist = manhattan(x, y, nx, ny)
        grid[nx][ny].probability += (0.3 / dist) * confidence

# Time decay (each tick)
for cell in grid:
    if not cell.survivor:  # don't decay confirmed finds
        cell.probability *= 0.97

# Cleared cell — hard reset
def mark_cleared(x, y):
    grid[x][y].probability = 0.0
    grid[x][y].searched = True
```

### Search Strategy Modes (agent selects dynamically)
| Mode | When | Behavior |
|---|---|---|
| **Spiral Sweep** | Mission start, no signals | Systematic outward coverage |
| **Gradient Ascent** | Signal detected | Drones move toward highest-prob cells |
| **Pincer** | Multiple signals near each other | Two scouts converge from opposite sides |
| **Perimeter Guard** | Fire spreading toward survivors | Medic dispatched on fastest safe path |
| **Recon** | Aftershock detected | All drones re-scan their current sector |

---

## 7. Communication Mesh Network

### Relay Architecture
```
Base Station ←─── Relay-1 ←─── Relay-2 ←─── Scout-A
(range: 10)       (range: 12)   (range: 12)   (at edge)
```
- Each drone maintains a `neighbors` list (drones within communication range)
- Messages hop through the mesh: `Scout → nearest relay → base → agent`
- Agent detects "island" drones (no path to base) and deploys relay automatically

### Communication Logic
```python
def is_reachable(drone_id) -> bool:
    """BFS through drone mesh to check if drone can reach base."""

def find_relay_point(isolated_drone) -> tuple:
    """Returns midpoint between base and isolated drone for relay placement."""

def mesh_health() -> float:
    """Returns % of active drones connected to base mesh."""
```

### Offline Data Sync
- Drones cache their scan results locally (simulated)
- When drone returns to base range, cached data is flushed to central map
- Enables true edge operation — drones work even when temporarily isolated

---

## 8. Mission Phases

```
PHASE 1: DEPLOYMENT   → Drones spread to assigned sectors
PHASE 2: SEARCH       → Systematic scanning, heatmap building
PHASE 3: CONVERGENCE  → Drones focus on high-probability zones
PHASE 4: CONFIRMATION → Swarm consensus on survivor locations
PHASE 5: RESCUE       → Medics dispatched, aid delivered
PHASE 6: EXTRACT      → All drones return, mission debrief
```

Phase transitions are **automatic** — agent evaluates:
- Phase 1→2: All drones reached initial positions
- Phase 2→3: Any cell probability > 0.6
- Phase 3→4: Any cell probability > 0.85 AND 2+ drones scanned it
- Phase 4→5: Consensus reached (see Section 5)
- Phase 5→6: All survivors rescued OR all drones low battery

---

## 9. Backend Server

### FastAPI Structure
```
backend/
├── main.py              # App entry, WebSocket manager, event bus
├── simulation.py        # Grid engine, tick loop, dynamic events
├── mcp_server.py        # FastMCP tool definitions
├── agent.py             # LangChain agent + loop
├── models/
│   ├── grid.py          # Cell, Grid dataclasses
│   ├── drone.py         # Drone dataclass + state machine
│   └── mission.py       # Mission, Survivor, Phase models
└── utils/
    ├── pathfinding.py   # A* implementation
    ├── heatmap.py       # Probability update logic
    └── mesh.py          # Communication mesh BFS
```

### API Endpoints
```
GET  /api/map            → Full grid state (snapshot)
GET  /api/drones         → All drone states
GET  /api/mission        → Mission status, phase, metrics
GET  /api/survivors      → Survivor list with conditions
POST /api/mission/start  → Start mission (body: {scenario, drone_count})
POST /api/mission/pause  → Pause simulation
POST /api/mission/reset  → Reset to fresh map
GET  /api/heatmap        → 2D probability array
WS   /ws/updates         → Real-time event stream
```

### WebSocket Event Types
```json
{ "event": "tick",              "data": { "tick": 42, "grid_delta": [...] } }
{ "event": "drone_moved",       "data": { "drone_id": "A1", "x": 5, "y": 7 } }
{ "event": "drone_altitude",    "data": { "drone_id": "M1", "altitude": 5, "state": "DELIVERING" } }
{ "event": "scan_result",       "data": { "drone_id": "A1", "cells": {...} } }
{ "event": "survivor_found",    "data": { "x": 12, "y": 8, "condition": "CRITICAL" } }
{ "event": "aid_delivered",     "data": { "survivor_id": "S1", "drone_id": "M1" } }
{ "event": "agent_thought",     "data": { "phase": "DECIDE", "text": "..." } }
{ "event": "phase_change",      "data": { "from": "SEARCH", "to": "CONVERGENCE" } }
{ "event": "aftershock",        "data": { "affected_cells": [...] } }
{ "event": "fire_spread",       "data": { "new_fire_cells": [...] } }
{ "event": "leader_changed",    "data": { "old": "A1", "new": "A2" } }
```

### Simulation Tick Engine
```python
async def simulation_loop():
    while mission.active:
        tick += 1
        update_fire_spread()
        update_debris()
        update_drone_positions()      # move each drone one step
        update_battery()
        update_heatmap_decay()
        check_survivor_deterioration()
        check_aftershock()
        broadcast_delta_to_clients()  # only changed cells, not full grid
        await asyncio.sleep(1.0 / TICK_RATE)
```

---

## 10. Frontend Dashboard

### Layout
```
┌──────────────────────────────────────────────────────┐
│  ARIA Command Center         [PHASE: SEARCH] Tick: 42│
├─────────────────────────┬────────────────────────────┤
│                         │  DRONE FLEET               │
│   2D COMMAND MAP        │  A1 Scout  ██████░  80%    │
│   (30×30 grid)          │  A2 Scout  ████░░░  55%    │
│                         │  M1 Medic  ███████  90%    │
│   🚁 = drone            │  R1 Relay  ██████░  75%    │
│   🔥 = fire             ├────────────────────────────┤
│   ❤️ = survivor         │  MISSION LOG (chain-of-    │
│   ■ = debris            │  thought streaming)        │
│   ░ = heatmap overlay   │  > OBSERVE: 3 drones active│
│                         │  > ASSESS: SE sector has   │
│   [Heatmap] [Risk]      │    high probability (0.73) │
│   [Mesh]  [Coverage]    │  > DECIDE: Send A2 to (18,2│
│                         │  > EXECUTE: move_to(A2,..) │
├─────────────────────────┴────────────────────────────┤
│  Survivors: 2/5 rescued │ Coverage: 67% │ Time: 1:42 │
└──────────────────────────────────────────────────────┘
```

### Map Overlay Modes (toggle buttons)
| Overlay | What it shows |
|---|---|
| **Heatmap** | Color gradient of survivor probability |
| **Risk** | Red zones for fire/high risk cells |
| **Mesh** | Lines showing drone communication links |
| **Coverage** | Blue = scanned, white = unsearched |
| **Paths** | Dashed lines showing drone planned routes |

### Map Interaction
- Click any cell → see cell details (probability, terrain, scan history)
- Click any drone → open Drone Detail Panel (or 3D view)
- Hover cell → tooltip with all cell properties

### 2D → 3D Architecture — Clean Separation

The key to easy 2D/3D switching: the data layer never changes, only the renderer.

```typescript
// Both views consume identical props — swap one component, nothing else changes
interface MapProps {
  grid: Cell[][]
  drones: Drone[]
  survivors: Survivor[]
  overlay: OverlayMode
}

// useSimulation hook owns all state (WebSocket, grid, drones) — shared by both views
const { grid, drones, survivors } = useSimulation()

// 2D: colored squares on <canvas>
<CommandMap2D grid={grid} drones={drones} survivors={survivors} overlay={overlay} />

// 3D: Three.js scene (swap in later, zero other code changes)
<CommandMap3D grid={grid} drones={drones} survivors={survivors} overlay={overlay} />
```

### How the 3D World Is Built from Grid Data

The grid has no height info — Three.js **derives** height from existing cell properties:

```
Ground height per cell:
  debris_level = 0  →  y = 0    (flat asphalt)
  debris_level = 1  →  y = 1.5  (light rubble)
  debris_level = 2  →  y = 3.0  (heavy collapsed structure)
  terrain = WATER   →  y = -1   (sunken / flooded)

Drone height:
  drone.altitude = 25  →  world y = 25  (CRUISING — reads real simulation value)
  drone.altitude = 15  →  world y = 15  (SCANNING)
  drone.altitude = 5   →  world y = 5   (DELIVERING — visibly descends to ground)
  drone.altitude = 20  →  world y = 20  (RETURNING)
```

Because `drone.altitude` is a real simulation field (not hardcoded), the 3D drone
**actually moves up and down** as the simulation changes its state. No faking.

### 3D Drone View — Floating Overlay on Drone Click

Priority: build after 2D map is working. Opens as a panel overlay when user clicks a drone.

**What it renders:**
- Drone 3D model with spinning rotors (speed based on `drone.status`)
- Drone smoothly lerps to `drone.altitude` each frame — real data, smooth visuals
- Scan cone (translucent blue frustum) visible when `status = SCANNING`
- Ground tiles below using grid cell data (terrain, debris, fire)
- Fire cells: flat tile + particle system + orange point light
- Drone descends visibly when delivering aid, ascends after

**Camera modes:**
- `FOLLOW` — orbits behind the drone at mid distance (default)
- `FIRST_PERSON` — attached to drone nose, looking forward/down
- `TOP_DOWN` — looking straight down, scan cone visible as circle below

**Atmosphere (makes it feel like a real disaster zone):**
```typescript
<fog attach="fog" args={["#c4a882", 80, 300]} />  // dusty brown haze
<ambientLight intensity={0.2} />                   // dark, grim
// fire cells emit dynamic orange light
{fireCells.map(c => <pointLight color="#ff6600" intensity={2} distance={30} />)}
```

### Mission Metrics Panel
```
┌─────────────────────────────────────┐
│  MISSION METRICS                    │
│  Coverage:      67% (████████░░░░)  │
│  Survivors:     2 rescued / 5 total │
│  Critical:      1 awaiting medic    │
│  Avg Confidence:0.73                │
│  Drone Uptime:  94%                 │
│  Mesh Health:   100% connected      │
│  Ticks elapsed: 42                  │
└─────────────────────────────────────┘
```

---

## 11. Scenario Configuration

Pre-built scenarios selectable from UI:
```json
{
  "EARTHQUAKE_ALPHA": {
    "grid_size": 30,
    "disaster_type": "EARTHQUAKE",
    "survivors": 5,
    "drones": { "scout": 2, "medic": 1, "relay": 1 },
    "fire_start_cells": 3,
    "debris_density": 0.3
  },
  "TYPHOON_BETA": {
    "grid_size": 30,
    "disaster_type": "TYPHOON",
    "survivors": 7,
    "drones": { "scout": 3, "medic": 2, "relay": 1 },
    "water_zones": true,
    "debris_density": 0.2
  },
  "STRESS_TEST": {
    "grid_size": 40,
    "disaster_type": "FIRE_DISASTER",
    "survivors": 10,
    "drones": { "scout": 3, "medic": 2, "relay": 2, "heavy": 1 },
    "fire_start_cells": 8,
    "aftershock_enabled": true
  }
}
```

---

## 12. Tech Stack

| Component | Technology | Why |
|---|---|---|
| Frontend | Next.js 14 + Tailwind CSS | Fast dev, SSR-ready |
| 3D Rendering | React Three Fiber + `@react-three/drei` | Declarative 3D, easy camera/controls |
| Backend | Python 3.11 + FastAPI | Async, fast prototyping |
| Simulation | Custom grid engine (+ Mesa optional) | Full control |
| LLM Agent | LangChain + `langchain-mcp-adapters` | MCP native support |
| LLM Provider | Gemini / DeepSeek / OpenAI / Claude (pick one) | API key in `.env` |
| MCP Server | FastMCP (Python) | Fastest MCP setup |
| Realtime | WebSocket (FastAPI native) | Low-latency updates |
| State | In-memory (Python dicts) | No DB needed for demo |

---

## 13. Folder Structure

```
rescue-swarm/
├── backend/
│   ├── main.py              # FastAPI app + WebSocket manager
│   ├── simulation.py        # Tick engine, grid, dynamic events
│   ├── mcp_server.py        # FastMCP tool definitions
│   ├── agent.py             # ARIA agent loop (LangChain)
│   ├── models/
│   │   ├── grid.py          # Cell, Grid
│   │   ├── drone.py         # Drone, DroneRole, DroneStatus
│   │   └── mission.py       # Mission, Survivor, Phase
│   └── utils/
│       ├── pathfinding.py   # A* with risk weights
│       ├── heatmap.py       # Probability map logic
│       └── mesh.py          # Communication mesh BFS
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   └── page.tsx     # Main layout
│   │   ├── components/
│   │   │   ├── CommandMap2D.tsx    # 2D grid renderer (canvas/SVG)
│   │   │   ├── DroneFleet.tsx      # Drone list sidebar
│   │   │   ├── MissionLog.tsx      # Agent thought stream
│   │   │   ├── MetricsPanel.tsx    # Coverage, survivors, etc.
│   │   │   ├── Drone3DView.tsx     # Three.js floating window
│   │   │   ├── HeatmapOverlay.tsx  # Canvas overlay
│   │   │   └── ScenarioSelector.tsx
│   │   ├── hooks/
│   │   │   ├── useSimulation.ts    # WebSocket state sync
│   │   │   └── useMapOverlay.ts    # Toggle overlay modes
│   │   └── lib/
│   │       └── types.ts            # Shared TypeScript types
│   └── package.json
│
├── scenarios/
│   └── presets.json         # Scenario configurations
│
├── .env.example             # LLM_PROVIDER, GOOGLE_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY
├── requirements.txt
└── README.md
```

---

## 14. MVP Build Order

### Phase A — Core Simulation (Day 1 AM)
- [ ] Grid model + drone model
- [ ] A* pathfinding with risk weights
- [ ] Basic drone movement + battery drain
- [ ] FastAPI server + WebSocket

### Phase B — MCP Server (Day 1 PM)
- [ ] FastMCP setup
- [ ] Core tools: `move_to`, `thermal_scan`, `get_battery_status`, `list_active_drones`
- [ ] Test tools manually via MCP inspector

### Phase C — LLM Agent (Day 1 PM / Eve)
- [ ] LangChain agent with MCP adapters
- [ ] System prompt + chain-of-thought format
- [ ] Basic observe → plan → act loop
- [ ] Streaming thoughts to WebSocket

### Phase D — Frontend (Day 2 AM)
- [ ] 2D grid renderer (canvas or SVG)
- [ ] WebSocket connection + state updates
- [ ] Drone list panel
- [ ] Mission log panel

### Phase E — Polish (Day 2 PM)
- [ ] Heatmap overlay
- [ ] Dynamic fire/debris events
- [ ] Swarm consensus protocol
- [ ] Scenario selector
- [ ] Three.js 3D drone view (if time allows — 2D must be fully working first)

---

## 15. Demo Script (Judge Walkthrough)

1. **Launch** — Select `EARTHQUAKE_ALPHA` scenario, click Start Mission
2. **Phase 1** — Show 2 scouts + 1 medic deploying to sectors on 2D map
3. **Agent thought** — Point to Mission Log, read agent's reasoning aloud
4. **Signal detected** — Scout finds thermal signature, heatmap lights up
5. **Consensus** — Second scout sent to confirm (show `request_confirmation` call)
6. **Fire event** — Trigger fire spread, show agent replanning path in real-time
7. **Medic dispatched** — Show medic navigating around fire using A* risk avoidance
8. **Aid delivered** — Survivor icon changes ✅, metrics panel updates
9. **Battery low** — Show drone autonomously returning before failure
10. **Leader election** — If demo permits: kill lead drone battery, show new leader
11. **Mission complete** — Coverage %, 2 survivors rescued, agent summary

---

## 16. Key Talking Points for Judges

| Theme | What to Say |
|---|---|
| **AI Agent** | "The LLM (Gemini/DeepSeek) acts as the autonomous brain — all decisions are reasoned, not hardcoded." |
| **MCP compliance** | "Every drone action goes through MCP tool calls — no hardcoded movement, full auditability." |
| **SDG relevance** | "ASEAN loses comms in first 72 hrs of a typhoon. This works in that blackout window." |
| **Swarm intelligence** | "Drones vote before dispatching a medic — no single point of failure in decisions." |
| **Real-time adaptation** | "Fire spread and aftershocks force the agent to replan mid-mission, live." |
