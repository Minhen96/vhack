# Search & Rescue Digital Twin - Frontend Controls

This document outlines the keyboard shortcuts and interaction patterns for the Multi-View Drone System.

## View Modes
- **GLOBAL (Command Overview)**: 
  - Standard bird's eye view of the disaster zone.
  - Controls: Panning (Left Click/Arrows), Zooming (Scroll), Rotating (Right Click).
- **FOLLOW (3rd Person)**: 
  - Damped camera tracking 5m behind the active drone.
  - Feel: Cinematic "Chase Cam" with organic lag.
- **PILOT (1st Person)**: 
  - Direct feed from the drone's primary sensor array.
  - Rotation: Strictly bound to drone telemetry (Azimuth/Elevation).
  - FOV: Ultra-wide 90° pilot perspective.

## Keyboard Shortcuts
| Key | Action |
|-----|--------|
| `G` / `Esc` | Return to **GLOBAL** View |
| `F` | Switch to **FOLLOW** View (Selected Drone) |
| `P` | Switch to **PILOT** View (Selected Drone) |
| `1` - `9` | Switch to Drone by index (Active Drones only) |

## Mouse Interactions
- **Drone List (Top Left)**: 
  - Click drone name to target.
  - Click `👁️` for Follow View.
  - Click `🚀` for Pilot View.
- **3D Environment**:
  - **Click Drone**: Cycle through views (Follow → Pilot → Global).
  - **Double-Click Ground**: Log coordinates for future "Move To" tactical commands.

## HUD Indicators
- **Left Scale**: Altitude Ladder (Meters from ground).
- **Top Scale**: Compass Tape (Degrees from North).
- **Center**: Reticle (Pilot mode only) for precision scouting.
- **Right Panel**: Real-time telemetry (Battery, Status, Drone ID).
