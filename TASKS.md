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

## Phase C — LLM Command Agent
> Goal: Agent autonomously runs the full observe → plan → act loop, streams thoughts

- [ ] `agent.py` — `build_llm()` with provider switch (Gemini / DeepSeek / OpenAI / Claude)
- [ ] `agent.py` — LangChain agent with `langchain-mcp-adapters` tool loading
- [ ] `agent.py` — system prompt: ARIA persona, constraints, chain-of-thought format
- [ ] `agent.py` — state summarizer: converts full grid → compact prompt string
- [ ] `agent.py` — agent loop as `asyncio.create_task` (decoupled from tick loop)
- [ ] `agent.py` — agent memory dict (cleared cells, confirmed survivors, relay positions)
- [ ] `agent.py` — emit `agent_thought` WebSocket events per reasoning phase
- [ ] Agent behavior: calls `list_active_drones()` at start of every cycle (no hardcoded IDs)
- [ ] Agent behavior: battery check before long assignments
- [ ] Agent behavior: swarm consensus — 2 scout confirms before medic dispatch
- [ ] Agent behavior: redeploy relay when drone goes out of mesh range
- [ ] Agent behavior: leader election awareness — replan when leader changes
- [ ] Test: agent completes a full EARTHQUAKE_ALPHA scenario end-to-end

---

## Phase D — Frontend 2D
> Goal: Live 2D map, drone list, mission log — all driven by WebSocket

- [ ] Next.js 14 project scaffold with Tailwind, TypeScript strict mode
- [ ] `lib/types.ts` — Cell, Drone, Survivor, MissionStatus, WebSocket event types
- [ ] `hooks/useSimulation.ts` — WebSocket connection, state sync, reconnect logic
- [ ] `hooks/useMapOverlay.ts` — toggle overlay modes (heatmap, risk, mesh, coverage, paths)
- [ ] `components/CommandMap2D.tsx` — canvas renderer, grid cells as colored squares
- [ ] `CommandMap2D` — drone icons positioned by grid coords
- [ ] `CommandMap2D` — survivor markers, fire cells, debris cells
- [ ] `CommandMap2D` — cell click → detail tooltip
- [ ] `CommandMap2D` — drone click → select drone, open detail panel
- [ ] `CommandMap2D` — heatmap overlay (color gradient from probability)
- [ ] `CommandMap2D` — path overlay (dashed lines to drone targets)
- [ ] `CommandMap2D` — mesh overlay (lines between drones in range)
- [ ] `components/DroneFleet.tsx` — drone list with battery bar, status, role, altitude
- [ ] `components/MissionLog.tsx` — streaming agent chain-of-thought, auto-scroll
- [ ] `components/MetricsPanel.tsx` — coverage %, survivors rescued, mesh health, ticks
- [ ] `components/ScenarioSelector.tsx` — scenario picker, drone count config, start button
- [ ] `app/page.tsx` — main layout wiring all components
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
