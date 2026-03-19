# Backend — Rescue Drone Command Server

The Python backend for the autonomous drone search-and-rescue system. It hosts the **MCP server** that exposes drone tools to the LLM Command Agent, the **REST API** for the frontend/map, and the **drone registry** that tracks all active drones on the network.

---

## Architecture

```
UI / Frontend
     │  REST (HTTP)
     ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI App  (port 8000)               │
│                                                     │
│  REST Endpoints            MCP Server               │
│  ├── GET  /api/map/drones  mounted at /mcp/mcp      │
│  ├── GET  /api/mission/*   (Streamable HTTP)        │
│  ├── POST /register                                 │
│  └── POST /deregister      ┌─────────────────────┐ │
│                             │   MCP Tools (10)    │ │
│  Command Agent (LLM)  ────▶│  list_active_drones │ │
│  LangChain + LangGraph      │  search_area        │ │
│  ReAct + Chain-of-Thought   │  move_to            │ │
│                             │  thermal_scan       │ │
│                             │  delivery_aid       │ │
│                             │  return_to_base     │ │
│                             │  request_backup     │ │
│                             │  get_drone_status   │ │
│                             │  get_battery_status │ │
│                             │  get_map_info       │ │
│                             └─────────────────────┘ │
│                                      │              │
│         DroneRegistry (in-memory)    │              │
│         tracks host:port of each drone              │
└─────────────────────────────────────────────────────┘
          │  HTTP calls to drone processes
          ▼
   Drone 1    Drone 2    Drone 3   ...
 (Go sim or real drone HTTP servers)
```

---

## Project Structure

```
backend/
├── main.py                    # FastAPI entry point, mounts MCP + routers
├── .env.example               # Copy to .env and fill in your API key
│
├── agent/
│   └── command_agent.py       # LLM agent — connects to MCP, runs missions
│
├── mcp/
│   └── server.py              # MCP server — exposes 10 drone tools
│
├── api/
│   └── routers/
│       ├── drone.py           # /register, /deregister, /api/map/drones
│       └── mission.py         # /api/mission/* (start, log, result, reset)
│
├── core/
│   └── drone_registry.py      # In-memory drone fleet store (singleton)
│
└── models/
    └── drone.py               # DroneState, DroneStatus, DroneCapability
```

---

## Setup

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv-mac
source .venv-mac/bin/activate      # macOS / Linux
# .venv-mac\Scripts\activate       # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your LLM API key:

```env
# Choose one provider: deepseek | gemini | openai | anthropic
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key_here

# MCP server URL (must match port below)
MCP_URL=http://localhost:8000/mcp/mcp

# Must match GRID_SIZE on the Go simulation server
GRID_SIZE=80
```

### 4. Run the server

```bash
uvicorn backend.main:app --reload --reload-exclude ".venv-mac" --port 8000
```

Server starts at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

---

## REST API Reference

### Drone Registry

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/register` | `{ drone_id, type, capabilities, host, port }` | Register a drone on startup |
| `POST` | `/deregister` | `{ drone_id }` | Remove a drone on shutdown |

**Register body fields:**

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| `drone_id` | string | `"drone-1"` | Unique ID |
| `type` | string | `"recon"` | Drone type label |
| `capabilities` | string[] | `["thermal_scan", "delivery_aid"]` | Known values: `thermal_scan`, `delivery_aid` |
| `host` | string | `"localhost"` | Drone's own HTTP host |
| `port` | int | `9001` | Drone's own HTTP port |

---

### Map

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/map/drones` | List all active (non-offline) drones with position, battery, status |

Response example:
```json
[
  { "drone_id": "drone-1", "x": 5, "y": 5, "z": 10, "battery_pct": 80.0, "status": "idle" },
  { "drone_id": "drone-2", "x": 15, "y": 10, "z": 10, "battery_pct": 95.0, "status": "idle" }
]
```

---

### Mission Control

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/mission/start` | Run a mission synchronously (blocks until complete) |
| `POST` | `/api/mission/start-background` | Run a mission in the background |
| `GET` | `/api/mission/log` | Poll real-time mission log (reasoning + tool calls) |
| `GET` | `/api/mission/result` | Get the final result of a background mission |
| `POST` | `/api/mission/reset` | Reset drone fleet to initial state |

**Mission request body:**
```json
{ "objective": "Search the entire disaster zone for survivors and deliver aid." }
```

---

## MCP Tools Reference

The agent discovers these tools automatically — they must never be hard-coded.

| Tool | Description |
|------|-------------|
| `list_active_drones` | Poll all registered drones and return live status |
| `get_drone_capabilities` | Return capabilities for a specific drone |
| `get_drone_status` | Return position, status, current task |
| `get_battery_status` | Return battery % (call `request_backup` if < 20%) |
| `move_to(drone_id, x, y, z)` | Move drone to coordinates |
| `thermal_scan(drone_id, radius)` | IR scan at current position, 5% battery cost |
| `search_area(drone_id, x1, y1, x2, y2, z, step)` | Autonomous snake-pattern sweep of a rectangular zone |
| `return_to_base(drone_id)` | Send drone back to (0,0) for charging |
| `delivery_aid(drone_id, x, y, z)` | Deliver supplies to target coordinates |
| `get_map_info` | Query sim server for map boundaries |
| `request_backup(drone_id)` | Dispatch nearest idle drone to replace a low-battery drone |

---

## MCP Endpoint (for Postman / direct testing)

The MCP server is mounted at:
```
POST http://localhost:8000/mcp/mcp
```

**Step 1 — Initialize session:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": { "name": "postman-test", "version": "1.0.0" }
  }
}
```
Copy the `mcp-session-id` from the response headers.

**Step 2 — Call a tool** (include `mcp-session-id` header):
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "list_active_drones",
    "arguments": {}
  }
}
```

---

## LLM Providers

| Provider | Env Var | Default Model |
|----------|---------|---------------|
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Gemini | `GOOGLE_API_KEY` | `gemini-2.0-flash` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |

Switch providers by changing `LLM_PROVIDER` in `.env`.

---

## Drone Status Values

| Status | Meaning |
|--------|---------|
| `idle` | Available for new tasks |
| `busy` | Currently executing a task |
| `returning` | Flying back to base |
| `charging` | At base, recharging |
| `offline` | Unreachable / shut down |
