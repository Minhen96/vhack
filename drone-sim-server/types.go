package main

// MessageType constants for WebSocket message types
const (
	MessageTypeInitConnection   = "init_connection"
	MessageTypeSendPosition     = "send_position"
	MessageTypeSurvivorDetected = "survivor_detected"
	MessageTypeGridSnapshot     = "grid_snapshot"
	MessageTypeGridUpdate       = "grid_update"
	MessageTypeScanHeatmap      = "scan_heatmap" // drone → hub → UI: raw thermal readings for heatmap
)

// =============================================================================
// UPLINK (Drone -> Server) Structs
// =============================================================================

// InitConnection represents the initial connection message sent by a drone
// when establishing a WebSocket connection to the server.
type InitConnection struct {
	Type        string       `json:"type"`
	DroneID     string       `json:"drone_id"`
	Timestamp   int64        `json:"timestamp"`
	Position    Position     `json:"position"`
	Capabilities Capabilities `json:"capabilities"`
}

// Position represents a 3D coordinate in space
type Position struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
	Z float64 `json:"z"`
}

// Capabilities represents the drone's sensor capabilities
type Capabilities struct {
	FOV        float64 `json:"fov"`
	ScanRadius float64 `json:"scan_radius"`
}

// SendPosition represents a position update message sent by a drone
type SendPosition struct {
	Type           string     `json:"type"`
	DroneID        string     `json:"drone_id"`
	Timestamp      int64      `json:"timestamp"`
	X              float64    `json:"x"`
	Y              float64    `json:"y"`
	Z              float64    `json:"z"`
	Spherical      Spherical  `json:"spherical"`
	ETAMS          int        `json:"eta_ms"`
}

// Spherical represents spherical coordinate data from drone sensors
type Spherical struct {
	Azimuth    float64 `json:"azimuth"`
	Elevation  float64 `json:"elevation"`
	ScanRadius float64 `json:"scan_radius"`
	FOV        float64 `json:"fov"`
}

// SurvivorDetected represents a survivor detection event from a drone
type SurvivorDetected struct {
	Type      string  `json:"type"`
	DroneID   string  `json:"drone_id"`
	Timestamp int64   `json:"timestamp"`
	X         float64 `json:"x"`
	Y         float64 `json:"y"`
	Z         float64 `json:"z"`
	Confidence float64 `json:"confidence"`
}

// =============================================================================
// DOWNLINK (Server -> Drone/UI) Structs
// =============================================================================

// GridSnapshot represents a complete grid state broadcast to all connected clients
type GridSnapshot struct {
	Type           string         `json:"type"`
	Timestamp      int64          `json:"timestamp"`
	Blocked        []BlockedArea  `json:"blocked"`
	CommandBase    *CommandBase   `json:"command_base,omitempty"`
}

// CommandBase represents the Command Base coordinates where drones spawn
type CommandBase struct {
	X float64 `json:"x"`
	Y float64 `json:"y"`
}

// BlockedArea represents an area of the grid that is blocked/obstructed
type BlockedArea struct {
	X      float64 `json:"x"`
	Y      float64 `json:"y"`
	Radius float64 `json:"radius"`
}

// GridUpdate represents an incremental grid state update
type GridUpdate struct {
	Timestamp      int64      `json:"timestamp"`
	Updates        []GridCell `json:"updates"`
}

// GridCell represents a single grid cell's passability state
type GridCell struct {
	X        float64 `json:"x"`
	Y        float64 `json:"y"`
	Passable bool    `json:"passable"`
}
