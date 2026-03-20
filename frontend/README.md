# The Command Center (RESCUE-ALPHA)
### Real-Time 3D Visualization & Mission Control

The Command Center is the high-performance visualization layer of the RESCUE-ALPHA digital twin. Built with **React Three Fiber (R3F)** and **Three.js**, it provides an immersive, data-dense interface for monitoring autonomous drone operations in real-time.

---

## Technical Architecture

The frontend is designed for **High-Frequency Telemetry Synchronization**. To handle 100Hz+ position updates without the UI bottlenecking, the system implements a mixed state-management strategy.

### State Management: Transient Ref Pattern
- **React State (Zustand)**: Used for UI overlays, mission logs, and slow-changing metadata (battery %, status labels).
- **Transient Refs**: Used for 3D object transformations (Position, Rotation, Scale). Components subscribe directly to the `dronesRef` to update Three.js matrices within the `useFrame` render loop, bypassing React's reconciliation for maximum GPU performance.

---

## 3D Environment: Digital Twin

The environment is a photorealistic reconstruction of an earthquake disaster zone.

### Key Visual Components
- **Photorealistic Terrain**: High-resolution ground plane featuring sunset lighting and dynamic dust particles.
- **Structural Models**: Procedural building collision geometry and instanced "Rubble" debris.
- **Thermal Heatmap Overlay**: A dynamic texture layer that accumulates thermal readings from the Swarm, rendered as an instanced mesh of colored tiles.
- **Conical FOV Visualizer**: Real-time rendering of each drone's camera frustum, synchronized with the drone's 3D orientation.

---

## Triple-View Camera System

The `CameraController` provides three synchronized perspectives for comprehensive mission awareness.

| View Mode | Perspective | Description |
|-----------|-------------|-------------|
| **GLOBAL** | Orbit Controls | Free-form 3D navigation around the entire simulation volume. |
| **FOLLOW** | 3rd-Person | High-damped spring-arm camera tracking a specific drone's trajectory. |
| **PILOT** | FPV (Pilot) | Cockpit-view from the drone's perspective, locked to its local coordinate system for maximum immersion. |

---

## UI/UX: Bento Bridge Interface

The overlay utilizes a **Glass-Bridge Bento UI** design, optimized for high-density information display.

### Functional Modules
- **Fleet Sidebar**: Real-time health monitor and selection for all active drones.
- **Tactical HUD**: 2D overlay providing compass heading, altitude ladder, and targeting reticles.
- **Mission Log**: Intelligent, scroll-anchored stream of LLM reasoning and mission events.
- **Intel Drawer**: Deep-dive telemetry for the selected drone (spherical coords, sensor status).

---

## Setup & Running

### Installation
```bash
cd frontend
npm install
```

### Execution
```bash
npm run dev
```
The interface will be available at `http://localhost:5173`.

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_WS_URL` | `ws://localhost:8080/ws/ui` | Destination for Map Engine telemetry. |
| `VITE_BACKEND_URL` | `http://localhost:8000` | Target for Mission Control REST API. |

---

## Spatial Coordinate Mapping

To maintain parity with the **Map Engine** (Go) and **Swarm** (Python), the frontend performs a coordinate transformation:

| Logic | RESCUE-ALPHA (Go/Py) | Three.js (React) |
|-------|--------------------|-------------------|
| **East/West** | `X` | `X` |
| **Altitude** | `Z` | `Y` |
| **North/South** | `Y` | `Z` |
