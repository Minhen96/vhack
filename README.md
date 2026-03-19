# Rescue Drone Simulation System

An autonomous multi-drone rescue simulation system for disaster response. An LLM agent commands a fleet of drones via the Model Context Protocol (MCP) to search for survivors using thermal imaging, navigate around obstacles with A\* pathfinding, and deliver aid — all visualized in a real-time 3D frontend.

## Architecture

```
LLM Agent (Backend MCP)
    │  calls MCP tools
    ▼
Backend  :8000   FastAPI — drone registry + MCP server
    │  HTTP
    ▼
Drone(s) :8001+  FastAPI — individual drone instances (A* nav, thermal scan)
    │  WebSocket + HTTP
    ▼
Sim Server :8080  Go — disaster zone simulator (survivors, buildings, thermal physics)
    │  WebSocket broadcast
    ▼
Frontend :5173   React + Three.js — real-time 3D visualizer
```

### Services

| Service | Language | Port | Description |
|---------|----------|------|-------------|
| `drone-sim-server` | Go | 8080 | WebSocket hub, occupancy grid, thermal physics |
| `backend` | Python | 8000 | MCP server, LLM agent, drone registry |
| `drone` | Python | 8001+ | Individual drone process (one per drone) |
| `frontend` | TypeScript/React | 5173 | Real-time 3D mission visualization |

## Prerequisites

| Tool | Version |
|------|---------|
| Go | 1.21+ |
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

## Quick Start (Automated)

The project includes scripts to automate setup and execution for different operating systems.

### Windows (PowerShell)
```powershell
# 1. Setup environment (venv, .env, deps)
.\dev.ps1 -Setup

# 2. Run all services
.\dev.ps1
```

### Linux / macOS (Bash)
```bash
# 1. Setup environment (venv, .env, deps)
chmod +x dev.sh
./dev.sh --setup

# 2. Run all services
./dev.sh
```

---

## Manual Setup (Detailed)

### 1. Clone the repository

```bash
git clone <repo-url>
cd vhack
```

### 2. Python virtual environment

```bash
# Create and activate venv
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Windows (cmd)
.venv\Scripts\activate.bat

# Install all Python dependencies
pip install -r requirements.txt
```

### 3. Go dependencies

```bash
cd drone-sim-server
go mod download
cd ..
```

### 4. Frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 5. Environment variables

Each service has its own `.env`. Copy the examples and fill in values:

```bash
# Backend LLM agent (API key required)
cp backend/.env.example backend/.env

# Drone process
cp drone/.env.example drone/.env

# Sim server (optional — defaults work out of the box)
cp drone-sim-server/.env.example drone-sim-server/.env

# Frontend (optional — defaults work out of the box)
cp frontend/.env.example frontend/.env
```

**Minimum required:** Set your LLM API key in `backend/.env`:

```dotenv
LLM_PROVIDER=deepseek          # deepseek | gemini | openai | anthropic
DEEPSEEK_API_KEY=your_key_here
```

See `.env.example` (root) for a full reference of all variables across all services.

## Running the System

Open **5 terminals** from the project root. Start services in order:

---

### Terminal 1 — Go Sim Server

**Linux / macOS / Git Bash:**
```bash
cd drone-sim-server
PORT=8080 go run . --server
```

**Windows (PowerShell):**
```powershell
cd drone-sim-server
$env:PORT="8080"
go run . --server
```

---

### Terminal 2 — Backend (MCP + LLM Agent)

```bash
uvicorn backend.main:app --port 8000 --reload
```

---

### Terminal 3 — Drone #1 (Scanner)

```bash
uvicorn drone.main:app --port 8001 --reload
```

> Uses `drone/.env` defaults: `DRONE_TYPE=scanner`, `DRONE_PORT=8001`

---

### Terminal 4 — Drone #2 (Delivery, optional)

**Linux / macOS / Git Bash:**
```bash
DRONE_TYPE=delivery DRONE_PORT=8002 uvicorn drone.main:app --port 8002
```

**Windows (PowerShell):**
```powershell
$env:DRONE_TYPE="delivery"
$env:DRONE_PORT="8002"
uvicorn drone.main:app --port 8002
```

---

### Terminal 5 — Frontend

```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Drone Types

| Type | Capabilities |
|------|-------------|
| `scanner` | Thermal camera — detects survivor heat signatures |
| `delivery` | Payload bay — delivers aid supplies to coordinates |

## LLM Providers

Set `LLM_PROVIDER` in `backend/.env` to one of:

| Provider | Key variable |
|----------|-------------|
| `deepseek` | `DEEPSEEK_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini` | `GOOGLE_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |

## MCP Tools (for LLM agent)

| Tool | Description |
|------|-------------|
| `list_active_drones` | Discover all registered drones |
| `get_drone_status` | Position, status, capabilities |
| `get_battery_status` | Battery level |
| `move_to` | Move drone to (x, y, z) with A\* pathfinding |
| `thermal_scan` | 360° thermal scan — detect survivors |
| `delivery_aid` | Deliver supplies to coordinates |
| `return_to_base` | Return drone to charging base |
| `request_backup` | Hand off mission to another drone |

## Port Reference

| Port | Service |
|------|---------|
| 8080 | Go Sim Server (WebSocket + HTTP) |
| 8000 | Backend FastAPI |
| 8001 | Drone #1 |
| 8002 | Drone #2 (optional) |
| 5173 | Frontend (Vite dev) |

## Battery Parameters

| Action | Drain |
|--------|-------|
| Movement | 0.5% per grid cell |
| Thermal scan | 1.0% |
| Delivery | 1.0% |
| Charging | +5% per second |
| Low battery alert | < 20% |
| Critical (no commands) | < 5% |
