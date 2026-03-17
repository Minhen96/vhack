# TASKS.md — Build Progress

Last updated: 2026-03-17
Phase A complete: 2026-03-17

---

## Status Legend
- `[ ]` Not started
- `[~]` In progress
- `[x]` Complete

---

## Phase A — Core Simulation & Backend Foundation ✅
> Goal: Grid runs, drones move, WebSocket streams state

- [x] Project scaffold — create folder structure (`backend/`, `frontend/`, `scenarios/`)
- [x] `models/grid.py` — `Cell` dataclass with all fields (terrain, fire, debris, survivor, probability)
- [x] `models/drone.py` — `Drone` dataclass with altitude + altitude_state fields
- [x] `models/mission.py` — `Mission`, `Survivor`, `Phase` models
- [x] `constants.py` — tick rate, grid size, altitude states, drain rates, risk weights
- [x] `simulation.py` — grid initializer, seeded map generation (EARTHQUAKE / TYPHOON / FIRE_DISASTER)
- [x] `simulation.py` — drone movement (one cell per tick along planned path)
- [x] `simulation.py` — battery drain per move per role
- [x] `simulation.py` — altitude state transitions (smooth 2 units/tick)
- [x] `simulation.py` — dynamic events: fire spread, fire burnout, debris shift
- [x] `simulation.py` — survivor deterioration (STABLE → CRITICAL after 60 ticks)
- [x] `simulation.py` — aftershock event (~120 ticks)
- [x] `utils/pathfinding.py` — A* with risk-weighted cost function
- [x] `utils/heatmap.py` — probability update, neighbor spread, time decay, clear cell
- [x] `utils/mesh.py` — BFS mesh reachability, relay midpoint finder, mesh health %
- [x] `main.py` — FastAPI app scaffold, CORS, lifespan
- [x] `main.py` — WebSocket manager (connect, disconnect, broadcast delta)
- [x] `main.py` — simulation tick loop as `asyncio.create_task`
- [x] REST endpoints: `GET /api/map`, `GET /api/drones`, `GET /api/mission`, `GET /api/survivors`, `GET /api/heatmap`
- [x] REST endpoints: `POST /api/mission/start`, `POST /api/mission/pause`, `POST /api/mission/reset`
- [x] WebSocket: broadcast delta on each tick (only changed cells, not full grid)

---

## Phase B — MCP Server ✅
> Goal: All drone tools exposed and callable, tested manually

- [x] `mcp_server.py` — FastMCP app setup
- [x] Discovery tools: `list_active_drones()`, `get_drone_status()`
- [x] Movement tools: `move_to()`, `assign_sector()`
- [x] Sensing tools: `thermal_scan()`, `deep_scan()`
- [x] Resource tools: `get_battery_status()`, `return_to_base()`, `deploy_relay()`
- [x] Rescue tools: `dispatch_medic()`, `deliver_aid()`
- [x] Environment tools: `get_map_state()`, `get_heatmap()`, `get_mission_status()`
- [x] Swarm tools: `broadcast_finding()`, `request_confirmation()`
- [x] Verify: `deliver_aid()` only succeeds when `drone.altitude == DELIVERING (5)`
- [x] Verify: `thermal_scan()` applies +0.15 confidence bonus when `drone.altitude == SCANNING (15)`
- [ ] Manual test: all tools via MCP inspector / curl

---

## Phase C — LLM Command Agent ✅
> Goal: Agent autonomously runs the full observe → plan → act loop, streams thoughts

- [x] `agent.py` — `build_llm()` with provider switch (Gemini / DeepSeek / OpenAI / Claude)
- [x] `agent.py` — LangChain ReAct agent with StructuredTool wrappers over MCP functions
- [x] `agent.py` — system prompt: ARIA persona, constraints, chain-of-thought format
- [x] `agent.py` — state summarizer: converts full grid → compact prompt string
- [x] `agent.py` — agent loop as `asyncio.create_task` (decoupled from tick loop)
- [x] `agent.py` — `AgentMemory` dataclass (cleared cells, confirmed survivors, relay positions)
- [x] `agent.py` — emit `agent_thought` WebSocket events per reasoning phase
- [x] Agent behavior: calls `list_active_drones()` at start of every cycle (no hardcoded IDs)
- [x] Agent behavior: battery check before long assignments (enforced via system prompt)
- [x] Agent behavior: swarm consensus — 2 scout confirms before medic dispatch
- [x] Agent behavior: redeploy relay when drone goes out of mesh range
- [x] Agent behavior: leader election awareness — replan when leader changes
- [ ] Test: agent completes a full EARTHQUAKE_ALPHA scenario end-to-end

---

## Phase D — Frontend 2D ✅
> Stack: Vite + React 18 + TypeScript strict + Tailwind + Zustand
> Goal: Live 2D map, drone list, mission log — all driven by WebSocket

- [x] Vite + React + TypeScript strict scaffold (replaced Next.js — zero SSR needed)
- [x] Tailwind CSS (PostCSS, dark command-center theme)
- [x] Zustand store (`store/simulation.ts`) — single source of truth for all sim state
- [x] `lib/types.ts` — Cell, Drone, Survivor, MissionStatus, all WebSocket event types
- [x] `hooks/useSimulation.ts` — WebSocket connection, full state sync, auto-reconnect
- [x] `hooks/useMapOverlay.ts` — toggle overlay modes (heatmap, risk, coverage, paths, mesh)
- [x] `components/CommandMap2D.tsx` — canvas renderer, terrain/fire/debris cells
- [x] `CommandMap2D` — drone icons positioned by grid coords, role colours, leader crown
- [x] `CommandMap2D` — survivor markers (yellow=stable, red=critical, grey=rescued)
- [x] `CommandMap2D` — cell hover → detail tooltip (terrain, fire, confidence, probability)
- [x] `CommandMap2D` — drone click → select drone
- [x] `CommandMap2D` — heatmap overlay (gradient from probability)
- [x] `CommandMap2D` — path overlay (dashed lines to drone targets)
- [x] `CommandMap2D` — mesh overlay (lines between drones in comm range)
- [x] `components/DroneFleet.tsx` — drone list, battery bar, role badge, status, altitude
- [x] `components/MissionLog.tsx` — streaming ARIA chain-of-thought, phase badges, auto-scroll
- [x] `components/MetricsPanel.tsx` — phase, tick, coverage %, survivors, connection status
- [x] `components/ScenarioSelector.tsx` — scenario picker, start/reset via REST
- [x] `App.tsx` — main layout wiring all components, overlay controls, pause/resume/reset
- [ ] Test: full mission playable in browser with live updates

---

## Phase E — 3D Drone View
> Goal: Clicking a drone opens a floating 3D panel that looks and feels real
> Only start this phase when Phase D is fully complete and stable

- [ ] Install React Three Fiber + `@react-three/drei` + `@react-three/postprocessing`
- [ ] `components/Drone3DView.tsx` — floating overlay panel (opens on drone click)
- [ ] Scene: fog, ambient light, directional light (low angle, disaster mood)
- [ ] Ground tiles: flat planes per visible cell, height derived from `cell.debris_level`
- [ ] Ground tiles: fire cells with particle system + orange point light
- [ ] Drone model: body + 4 rotors (spin speed based on `drone.status`)
- [ ] Drone position: lerp to `gridToWorld(drone.x, drone.y)` each frame
- [ ] Drone altitude: lerp to `drone.altitude` each frame (reads real simulation value)
- [ ] Scan cone: translucent blue frustum visible when `status == SCANNING`
- [ ] Delivery animation: drone descends to y=5 visibly, aid particle burst, ascends
- [ ] Camera mode — `FOLLOW`: orbit behind drone
- [ ] Camera mode — `FIRST_PERSON`: attached to drone nose
- [ ] Camera mode — `TOP_DOWN`: looking straight down at drone
- [ ] Post-processing: bloom on fire lights + survivor marker glow

---

## Phase F — Final Polish & Demo Prep
> Goal: Stable demo, no crashes, judge walkthrough rehearsed

- [ ] `.env.example` with all provider keys documented
- [ ] `scenarios/presets.json` — EARTHQUAKE_ALPHA, TYPHOON_BETA, STRESS_TEST
- [ ] End-to-end test: full EARTHQUAKE_ALPHA run without intervention
- [ ] Verify: agent never hardcodes drone IDs (check logs)
- [ ] Verify: all drone actions go through MCP (no direct simulation calls from agent)
- [ ] Verify: simulation tick and agent loop never block each other
- [ ] Rehearse demo script from plan.md Section 15
- [ ] README.md — setup instructions, how to run, how to switch LLM provider

---

## Completed

- [x] 2026-03-17 — Phase A complete: full backend simulation, models, utils, FastAPI + WebSocket server
- [x] 2026-03-17 — Backend refactored to industry-standard structure (core/, api/, routers split, DI pattern, standardised API responses)
- [x] 2026-03-17 — Phase B complete: all MCP tools implemented in mcp_server.py
- [x] 2026-03-17 — Phase C complete: ARIA agent loop, LLM provider switch, memory, WS streaming
- [x] 2026-03-17 — Phase D complete: Vite+React frontend, canvas map, drone fleet, ARIA log, scenario selector
