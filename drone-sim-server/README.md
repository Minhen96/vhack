# Drone Simulation WebSocket Server

A high-performance WebSocket server and client for simulating drone swarm coordination in rescue missions.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [API Contracts](#api-contracts)
- [Running Multiple Drones](#running-multiple-drones)
- [Configuration](#configuration)

---

## Overview

This project implements a WebSocket-based communication system for drone swarm simulation. It consists of:

1. **Server** (`main.go`): A WebSocket hub that manages drone connections and broadcasts telemetry to UI clients
2. **Mock Drone Client** (`drone.go`): A simulated drone that flies a lawnmower search pattern and sends position updates

The system is designed for:
- **High concurrency**: Uses Go channels and single-writer pattern for thread-safe WebSocket operations
- **Automatic reconnection**: Clients automatically reconnect with exponential backoff on disconnect
- **Real-time telemetry**: Drones send position updates every 200ms

---

## Prerequisites

### Install Go (Windows)

1. Download Go from [https://go.dev/dl/](https://go.dev/dl/)
2. Run the installer (e.g., `go1.21.x.windows-amd64.msi`)
3. Verify installation:
   ```cmd
   go version
   ```

### Install Go (macOS)

```bash
# Using Homebrew
brew install go

# Or download from https://go.dev/dl/
```

### Install Go (Linux)

```bash
# Ubuntu/Debian
sudo apt-get install golang-go

# Or download from https://go.dev/dl/
```

---

## Installation

1. Clone the repository:
   ```bash
   cd drone-sim-server
   ```

2. Download dependencies:
   ```bash
   go mod download
   ```

3. Build the binaries:
   ```bash
   # Build server
   go build -o drone-server.exe .

   # Build client
   go build -o drone-client.exe . -drone
   ```

---

## Quick Start

### Running the Server

```bash
# Using go run
go run . -server

# Or using built binary
drone-server.exe
```

The server starts on `http://localhost:8080` by default.

### Running the Drone Client

```bash
# Using go run
go run . -drone

# Or using built binary
drone-client.exe
```

### Expected Output

**Server:**
```
2026/03/18 23:26:35 Starting WebSocket Hub on port 8080
2026/03/18 23:26:35 Server listening on http://localhost:8080
2026/03/18 23:26:40 📡 Drone client registered: drone_1 (Total drones: 1)
```

**Client:**
```
🔗 Connecting to ws://localhost:8080/ws/drone?drone_id=drone_1
✅ Connected successfully as drone: drone_1
📥 Received grid_snapshot: {...}
🚀 Starting tick loop (interval: 200ms)

╔══════════════════════════════════════════════════════════════╗
║  🛸 DRONE STATUS                                               ║
╠══════════════════════════════════════════════════════════════╣
║  Drone ID:     drone_1                                      ║
║  Position:    (X:    0.0, Y:  15.0, Z:    4.0)               ║
║  Altitude:    15.0                                          m║
║  Azimuth:     270.0                                        °║
║  Heading:     WEST (←)                                     ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Architecture

### Server Components

```
┌─────────────────────────────────────────────────────────────┐
│                     WebSocket Server                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌─────────────┐  │
│  │   Hub        │◄──►│   Client     │◄──►│  WebSocket  │  │
│  │  (Manager)   │    │  (Per Conn)  │    │  Upgrader   │  │
│  └──────┬───────┘    └──────────────┘    └─────────────┘  │
│         │                                                   │
│    ┌────┴────┬──────────────┐                              │
│    │         │              │                               │
│    ▼         ▼              ▼                               │
│ ┌──────┐ ┌────────┐ ┌───────────┐                         │
│ │Drone │ │   UI   │ │ Broadcast │                         │
│ │Clients│ │Clients │ │  Channel  │                         │
│ └──────┘ └────────┘ └───────────┘                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Client Components

```
┌─────────────────────────────────────────────────────────────┐
│                   Mock Drone Client                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐                    │
│  │ Tick Loop    │───►│  Write Chan   │───►│  Write Pump   │
│  │ (200ms)      │    │  (buffered)  │    │  (single)     │
│  └──────┬───────┘    └──────────────┘    └──────────────┘ │
│         │                                                   │
│    ┌────▼────┐                                              │
│    │ Position│                                              │
│    │ Update  │                                              │
│    └─────────┘                                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Connection Flow

1. **Drone connects** → Server upgrades HTTP to WebSocket
2. **Drone sends init_connection** → Server registers drone, sends grid_snapshot
3. **Drone sends position updates** (every 200ms) → Server broadcasts to UI clients
4. **Server sends periodic pings** (every 25s) → Drone responds with pongs

---

## API Contracts

### WebSocket Endpoints

| Endpoint | Description |
|----------|-------------|
| `/ws/drone` | WebSocket endpoint for drone connections |
| `/ws/ui` | WebSocket endpoint for UI clients |
| `/health` | HTTP health check endpoint |

### Message Types (Constants)

```go
const (
    MessageTypeInitConnection   = "init_connection"
    MessageTypeSendPosition     = "send_position"
    MessageTypeSurvivorDetected = "survivor_detected"
    MessageTypeGridSnapshot     = "grid_snapshot"
    MessageTypeGridUpdate      = "grid_update"
)
```

---

### 1. Init Connection (Drone → Server)

Sent by drone immediately after connecting.

```json
{
    "type": "init_connection",
    "drone_id": "drone_1",
    "timestamp": 1773846533000000000,
    "position": {
        "x": 0.0,
        "y": 15.0,
        "z": 0.0
    },
    "capabilities": {
        "fov": 60,
        "scan_radius": 5
    }
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"init_connection"` |
| `drone_id` | string | Unique identifier for the drone |
| `timestamp` | int64 | Unix timestamp in nanoseconds |
| `position.x` | float64 | X coordinate |
| `position.y` | float64 | Y coordinate (altitude) |
| `position.z` | float64 | Z coordinate |
| `capabilities.fov` | int | Field of view in degrees |
| `capabilities.scan_radius` | int | Detection scan radius |

---

### 2. Send Position (Drone → Server)

Sent by drone every 200ms with current position.

```json
{
    "type": "send_position",
    "drone_id": "drone_1",
    "timestamp": 1773846534000000000,
    "x": 50.0,
    "y": 15.0,
    "z": 25.0,
    "spherical": {
        "azimuth": 90.0,
        "elevation": -90,
        "scan_radius": 5,
        "fov": 60
    },
    "eta_ms": 200
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"send_position"` |
| `drone_id` | string | Unique identifier for the drone |
| `timestamp` | int64 | Unix timestamp in nanoseconds |
| `x` | float64 | X coordinate |
| `y` | float64 | Y coordinate (altitude) |
| `z` | float64 | Z coordinate |
| `spherical.azimuth` | float64 | Compass heading (0=North, 90=East, 180=South, 270=West) |
| `spherical.elevation` | float64 | Sensor elevation angle |
| `spherical.scan_radius` | int | Current scan radius |
| `spherical.fov` | int | Field of view in degrees |
| `eta_ms` | int | Time between updates in milliseconds |

---

### 3. Grid Snapshot (Server → Drone)

Sent by server to new clients after connection.

```json
{
    "type": "grid_snapshot",
    "timestamp": 1773846533000,
    "blocked": [
        {
            "x": 10,
            "y": 10,
            "radius": 5
        },
        {
            "x": 25,
            "y": 30,
            "radius": 8
        }
    ]
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"grid_snapshot"` |
| `timestamp` | int64 | Unix timestamp in milliseconds |
| `blocked[].x` | float64 | X coordinate of blocked area center |
| `blocked[].y` | float64 | Y coordinate of blocked area center |
| `blocked[].radius` | float64 | Radius of blocked area |

---

### 4. Survivor Detected (Drone → Server)

Optional message when drone detects a survivor.

```json
{
    "type": "survivor_detected",
    "drone_id": "drone_1",
    "timestamp": 1773846540000000000,
    "x": 45.5,
    "y": 0.0,
    "z": 32.2,
    "confidence": 0.85
}
```

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"survivor_detected"` |
| `drone_id` | string | ID of drone that detected survivor |
| `timestamp` | int64 | Unix timestamp in nanoseconds |
| `x` | float64 | X coordinate of survivor |
| `y` | float64 | Y coordinate of survivor |
| `z` | float64 | Z coordinate of survivor |
| `confidence` | float64 | Detection confidence (0.0 - 1.0) |

---

## Running Multiple Drones

To simulate a swarm, run multiple drone clients with different IDs:

```bash
# Terminal 1: Start server
go run . -server

# Terminal 2: Start drone 1
go run . -drone -drone-id=drone_1

# Terminal 3: Start drone 2
go run . -drone -drone-id=drone_2

# Terminal 4: Start drone 3
go run . -drone -drone-id=drone_3
```

Each drone will fly its own lawnmower pattern starting from different positions.

---

## Configuration

### Server Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8080` | Server port |
| `ALLOWED_ORIGINS` | (all) | Comma-separated list of allowed CORS origins |

### Client Configuration

The client can be configured via command-line flags or by modifying the `LawnmowerConfig` in `drone.go`:

```go
config := LawnmowerConfig{
    GridMinX: 0.0,   // Grid minimum X
    GridMaxX: 100.0,  // Grid maximum X
    GridMinZ: 0.0,    // Grid minimum Z
    GridMaxZ: 100.0,  // Grid maximum Z
    StepSize: 2.0,    // Movement step per tick
    MaxRows: 50,      // Maximum rows in pattern
}
```

### Timeout Configuration

| Constant | Default | Description |
|----------|---------|-------------|
| `ServerPingInterval` | 25s | Server ping interval |
| `ServerReadDeadline` | 60s | Server read timeout |
| `ServerWriteDeadline` | 10s | Server write timeout |
| `pingInterval` | 20s | Client ping interval |
| `readDeadline` | 60s | Client read timeout |
| `writeTimeout` | 10s | Client write timeout |

---

## Troubleshooting

### "Address already in use"

The port is already in use. Kill existing processes:

```cmd
# Windows
taskkill /F /IM drone-server.exe
```

### Connection refused

Ensure the server is running before starting the client.

### High latency or disconnections

Check network conditions and adjust timeout values in the code if needed.

---

## License

MIT
