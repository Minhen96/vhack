# RESCUE-ALPHA
### Autonomous Search & Rescue Digital Twin

<p align="center">
  <img src="assets/logo.png" alt="RESCUE-ALPHA Logo" width="200" />
</p>

<p align="center">
  <img src="assets/banner.jpg" alt="RESCUE-ALPHA Banner" width="800" />
</p>

<p align="center">
  <a href="https://go.dev"><img src="https://img.shields.io/badge/Go-1.21+-00ADD8?style=flat&logo=go" alt="Go"></a>
  <a href="https://react.dev"><img src="https://img.shields.io/badge/React-18+-61DAFB?style=flat&logo=react" alt="React"></a>
  <a href="https://threejs.org"><img src="https://img.shields.io/badge/Three.js-r160+-000000?style=flat&logo=three.js" alt="Three.js"></a>
  <a href="https://www.typescriptlang.org"><img src="https://img.shields.io/badge/TypeScript-5.0+-3178C6?style=flat&logo=typescript" alt="TypeScript"></a>
  <a href="https://modelcontextprotocol.io"><img src="https://img.shields.io/badge/MCP-1.0-orange?style=flat" alt="MCP"></a>
</p>

---

## Executive Summary
**RESCUE-ALPHA** is a high-performance, distributed simulation system designed for autonomous earthquake disaster response. It utilizes a state-of-the-art **4-node architecture** that synchronizes real-time 3D visualization, high-concurrency telemetry handling, and LLM-driven autonomous orchestration via the Model Context Protocol (MCP).

The system enables a fleet of heterogeneous drones (Scanners and Delivery units) to systematically search for human heat signatures in rubble fields, navigate complex obstacles using A* pathfinding, and deliver life-saving aid—all without human intervention.

---

## System Architecture

RESCUE-ALPHA operates on two primary planes: the **Telemetry Plane** (Spatial Synchronization) and the **Control Plane** (Autonomous Orchestration).

```mermaid
flowchart TB
    subgraph UI_Layer ["1. The Command Center (Frontend)"]
        UI[React Three Fiber 3D Interface]
        HUD[Tactical HUD & Bento UI]
    end

    subgraph Hub_Layer ["2. The Map Engine (Golang Hub)"]
        Hub[WebSocket Hub]
        ThermalEngine[Thermal Physics Engine]
        Grid[Occupancy Grid]
    end

    subgraph Swarm_Layer ["3. The Swarm (Drones)"]
        D1[Drone #1: Scanner]
        D2[Drone #2: Delivery]
        DN[Drone #N: Isolated Processes]
    end

    subgraph Agent_Layer ["4. The Commander (LLM Agent)"]
        Agent[LangChain Agent]
        MCP[MCP Server]
    end

    %% Telemetry Flow
    D1 -.->|JSON Telemetry| Hub
    D2 -.->|JSON Telemetry| Hub
    Hub -.->|Broadcast| UI
    
    %% Physics Queries
    D1 <-->|HTTP /scan| ThermalEngine
    
    %% Control Flow
    Agent <-->|MCP Protocol| MCP
    MCP <-->|HTTP Control| D1
    MCP <-->|HTTP Control| D2
    
    %% External AI
    Agent <-->|LLM API| LLM[External LLM Provider]

    style UI_Layer fill:#1a1a1a,stroke:#333,color:#fff
    style Hub_Layer fill:#002b36,stroke:#008b8b,color:#fff
    style Swarm_Layer fill:#2c3e50,stroke:#34495e,color:#fff
    style Agent_Layer fill:#2d1b4d,stroke:#5e2a84,color:#fff
```

### The Four Pillars
1.  **[The Command Center (Frontend)](file:///d:/Projects/vhack/frontend/README.md)**: A React-based 3D digital twin of the disaster zone, featuring a triple-view camera system (Global, Follow, Pilot) and real-time thermal heatmap rendering.
2.  **[The Map Engine (drone-sim-server)](file:///d:/Projects/vhack/drone-sim-server/README.md)**: A high-concurrency Golang WebSocket hub utilizing non-blocking I/O to handle 100Hz+ telemetry streams with zero backpressure.
3.  **[The Swarm (drone-processes)](file:///d:/Projects/vhack/drone/README.md)**: Isolated Python processes simulating physical hardware, A* navigation, and 3D conical FOV (Field of View) thermal detection.
4.  **[The Commander (backend)](file:///d:/Projects/vhack/backend/README.md)**: An LLM-powered orchestration engine that communicates via the Model Context Protocol (MCP) to manage the fleet as a set of autonomous tools.

---

## Orchestration Guide

### Prerequisites
- **Go 1.21+** (Map Engine)
- **Node.js 18+** (Frontend)
- **Python 3.11+** (Drones & Agent)
- **LLM API Key** (DeepSeek, Gemini, OpenAI, or Anthropic)

### Startup Sequence
To ensure proper handshaking between nodes, start the services in the following order:

1.  **Map Engine**: `cd drone-sim-server && go run main.go --server`
2.  **Drone Swarm**: Start as many drones as needed in separate terminals.
    - `cd drone && python main.py` (Default: Scanner at port 8001)
    - `DRONE_TYPE=delivery DRONE_PORT=8002 python main.py`
3.  **Commander Agent**: `cd backend && uvicorn backend.main:app --port 8000`
4.  **Command Center**: `cd frontend && npm run dev`

### Automated Deployment (Windows)
```powershell
.\dev.ps1 -Setup  # Install all dependencies and create venvs
.\dev.ps1         # Launch all 5+ terminals automatically
```

---

## Core Technologies

| Layer | Stack | Key Features |
|-------|-------|--------------|
| **Frontend** | React, R3F, Drei, Zustand | Transient Ref Pattern, Triple-View Camera, Bento UI |
| **Sim Server** | Go, lxzan/gws | Non-blocking WebSocket Hub, Non-pressure Telemetry |
| **Drone AI** | Python, FastAPI, A* | Conical FOV simulation, Battery management, Lawnmower search |
| **Command Agent** | Python, LangChain, MCP | Model Context Protocol, Chain-of-Thought Reasoning |

---

## Component Deep Dives

- **[Architecture & Orchestration (Backend)](file:///d:/Projects/vhack/backend/README.md)**
- **[3D Visualization (Frontend)](file:///d:/Projects/vhack/frontend/README.md)**
- **[Telemetry Hub (Go Sim Server)](file:///d:/Projects/vhack/drone-sim-server/README.md)**
- **[Drone Simulation (Python Swarm)](file:///d:/Projects/vhack/drone/README.md)**

---

