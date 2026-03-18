package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/url"
	"os"
	"time"

	"github.com/gorilla/websocket"
)

// =============================================================================
// Connection Configuration Constants
// =============================================================================

const (
	defaultWsURL = "ws://localhost:8080/ws/drone"

	// Reconnection settings with exponential backoff
	initialReconnectDelay = 1 * time.Second  // Start with 1 second
	maxReconnectDelay     = 30 * time.Second // Cap at 30 seconds
	reconnectMultiplier   = 2.0               // Double delay each attempt

	// Connection health settings
	pingInterval       = 20 * time.Second  // Send ping every 20 seconds
	pongWaitTimeout    = 30 * time.Second  // Wait for pong within 30 seconds
	writeTimeout       = 10 * time.Second  // Write message timeout
	readDeadline       = 60 * time.Second   // Read deadline for messages (longer for stability)
	initialReadTimeout = 60 * time.Second  // Initial connection read timeout (longer)
)

// =============================================================================
// MockDrone represents a mock drone WebSocket client
// =============================================================================

type MockDrone struct {
	conn         *websocket.Conn
	droneID      string
	serverURL    string
	currentX     float64
	currentZ     float64
	altitude     float64
	tickInterval time.Duration

	// Reconnection state
	reconnectDelay    time.Duration
	maxReconnectAttempts int
	isConnected       bool

	// Lawnmower pattern state
	gridMinX   float64
	gridMaxX   float64
	gridMinZ   float64
	gridMaxZ   float64
	stepSize   float64
	isMovingX  bool // true = moving along X axis, false = moving along Z axis
	direction  int  // 1 or -1 for positive/negative direction
	currentRow int
	maxRows    int

	// Write channel for the single-writer pattern
	// All writes go through this channel, processed by writePump
	writeChan chan []byte

	// Run control
	stopChan chan struct{}
	doneChan chan struct{}
}

// LawnmowerConfig defines the search pattern parameters
type LawnmowerConfig struct {
	GridMinX float64
	GridMaxX float64
	GridMinZ float64
	GridMaxZ float64
	StepSize float64
	MaxRows  int
}

// NewMockDrone creates a new mock drone client instance
func NewMockDrone(droneID string, config LawnmowerConfig) *MockDrone {
	return &MockDrone{
		droneID:               droneID,
		serverURL:              defaultWsURL,
		currentX:               config.GridMinX,
		currentZ:               config.GridMinZ,
		altitude:               15.0,
		tickInterval:           200 * time.Millisecond,
		gridMinX:               config.GridMinX,
		gridMaxX:               config.GridMaxX,
		gridMinZ:               config.GridMinZ,
		gridMaxZ:               config.GridMaxZ,
		stepSize:               config.StepSize,
		isMovingX:              true,
		direction:              1,
		currentRow:             0,
		maxRows:                config.MaxRows,
		reconnectDelay:         initialReconnectDelay,
		maxReconnectAttempts:   0, // Unlimited retries
		isConnected:            false,
		writeChan:              make(chan []byte, 256), // Buffered channel for writes
		stopChan:               make(chan struct{}),
		doneChan:               make(chan struct{}),
	}
}

// Connect establishes WebSocket connection to the server with ping/pong handling
func (d *MockDrone) Connect() error {
	u, err := url.Parse(d.serverURL)
	if err != nil {
		return fmt.Errorf("failed to parse URL: %w", err)
	}

	query := u.Query()
	query.Set("drone_id", d.droneID)
	u.RawQuery = query.Encode()

	log.Printf("🔗 Connecting to %s", u.String())

	// Create custom dialer with timeouts
	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}

	conn, _, err := dialer.Dial(u.String(), nil)
	if err != nil {
		return fmt.Errorf("failed to connect to WebSocket: %w", err)
	}

	// Configure connection for keep-alive
	conn.SetReadLimit(512 * 1024)
	conn.SetReadDeadline(time.Now().Add(initialReadTimeout))
	conn.SetWriteDeadline(time.Now().Add(writeTimeout))

	// Set pong handler to reset read deadline
	conn.SetPongHandler(func(string) error {
		conn.SetReadDeadline(time.Now().Add(readDeadline))
		return nil
	})

	d.conn = conn
	d.isConnected = true
	log.Printf("✅ Connected successfully as drone: %s", d.droneID)

	// Start write pump (single-writer pattern)
	go d.writePump()

	// Start ping handler in background
	go d.handlePingPong()

	return nil
}

// handlePingPong sends periodic pings to keep connection alive
func (d *MockDrone) handlePingPong() {
	pingTicker := time.NewTicker(pingInterval)
	defer pingTicker.Stop()

	for {
		select {
		case <-pingTicker.C:
			if !d.isConnected || d.conn == nil {
				return
			}
			// Send ping through write channel (single-writer pattern)
			select {
			case d.writeChan <- []byte{}:
				log.Printf("📶 Queued ping to server")
			default:
				log.Printf("⚠️  Write channel full, skipping ping")
			}

		case <-d.stopChan:
			return
		}
	}
}

// writePump is the single writer goroutine that processes all WebSocket writes
// This prevents concurrent write errors
func (d *MockDrone) writePump() {
	// Create ping ticker
	pingTicker := time.NewTicker(pingInterval)
	defer func() {
		pingTicker.Stop()
		if d.conn != nil {
			d.conn.Close()
		}
	}()

	for {
		select {
		case message, ok := <-d.writeChan:
			if !ok {
				// Channel closed
				d.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			d.conn.SetWriteDeadline(time.Now().Add(writeTimeout))
			if err := d.conn.WriteMessage(websocket.TextMessage, message); err != nil {
				log.Printf("❌ Write error: %v", err)
				d.handleDisconnection("write failed")
				return
			}

		case <-pingTicker.C:
			// Send periodic ping
			d.conn.SetWriteDeadline(time.Now().Add(writeTimeout))
			if err := d.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("⚠️  Ping failed: %v", err)
				d.handleDisconnection("ping failed")
				return
			}
			log.Printf("📶 Sent ping to server")

		case <-d.stopChan:
			log.Printf("📤 WritePump: received stop signal")
			return
		}
	}
}

// SendInitConnection sends the initial connection message
func (d *MockDrone) SendInitConnection() error {
	if d.conn == nil {
		return fmt.Errorf("not connected")
	}

	msg := InitConnection{
		Type:      MessageTypeInitConnection,
		DroneID:   d.droneID,
		Timestamp: time.Now().UnixNano(),
		Position: Position{
			X: d.currentX,
			Y: d.altitude,
			Z: d.currentZ,
		},
		Capabilities: Capabilities{
			FOV:        60,
			ScanRadius: 5,
		},
	}

	// Marshal and send through write channel
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal init_connection: %w", err)
	}

	select {
	case d.writeChan <- data:
		log.Printf("📤 Sent init_connection: drone_id=%s, position=(%.1f, %.1f, %.1f)",
			d.droneID, d.currentX, d.altitude, d.currentZ)
		return nil
	default:
		return fmt.Errorf("write channel full")
	}
}

// WaitForGridSnapshot waits for and processes the grid_snapshot message
func (d *MockDrone) WaitForGridSnapshot() error {
	if d.conn == nil {
		return fmt.Errorf("not connected")
	}

	log.Println("⏳ Waiting for grid_snapshot...")

	// Set read deadline
	d.conn.SetReadDeadline(time.Now().Add(initialReadTimeout))

	_, message, err := d.conn.ReadMessage()
	if err != nil {
		return fmt.Errorf("failed to read message: %w", err)
	}

	var msg map[string]interface{}
	if err := json.Unmarshal(message, &msg); err != nil {
		return fmt.Errorf("failed to unmarshal message: %w", err)
	}

	msgType, ok := msg["type"].(string)
	if !ok {
		return fmt.Errorf("message type not found")
	}

	if msgType == MessageTypeGridSnapshot {
		log.Printf("📥 Received grid_snapshot:")
		log.Printf("   %s", formatJSON(message))
	} else {
		log.Printf("⚠️  Received unexpected message type: %s", msgType)
	}

	return nil
}

// CalculateAzimuth calculates the azimuth angle based on movement direction
// 0=North (positive Z), 90=East (positive X), 180=South (negative Z), 270=West (negative X)
func (d *MockDrone) CalculateAzimuth() float64 {
	var azimuth float64

	if d.isMovingX {
		// Moving along X axis
		if d.direction > 0 {
			// Moving positive X = East = 90
			azimuth = 90.0
		} else {
			// Moving negative X = West = 270
			azimuth = 270.0
		}
	} else {
		// Moving along Z axis
		if d.direction > 0 {
			// Moving positive Z = North = 0
			azimuth = 0.0
		} else {
			// Moving negative Z = South = 180
			azimuth = 180.0
		}
	}

	return azimuth
}

// UpdatePosition updates the drone's position based on lawnmower pattern
// Lawnmower pattern: start at (0,0), go East to right edge, go North one row,
// go West to left edge, go North one row, repeat until reaching top edge
func (d *MockDrone) UpdatePosition() {
	if d.isMovingX {
		// Move along X axis
		d.currentX += d.stepSize * float64(d.direction)

		// Check if we've reached the X boundary
		if d.currentX >= d.gridMaxX {
			d.currentX = d.gridMaxX
			// Reached right edge: go North (positive Z)
			d.direction = 1
			d.isMovingX = false
		} else if d.currentX <= d.gridMinX {
			d.currentX = d.gridMinX
			// Reached left edge: go North (positive Z)
			d.direction = 1
			d.isMovingX = false
		}
	} else {
		// Move along Z axis (to next row)
		d.currentZ += d.stepSize * float64(d.direction)

		// Check if we've reached the Z boundary
		if d.currentZ >= d.gridMaxZ {
			// Reached top of grid: loop back to start
			d.currentZ = d.gridMinZ
			d.currentX = d.gridMinX
			d.direction = 1 // Go East
			d.isMovingX = true
		} else if d.currentZ <= d.gridMinZ {
			// Should not happen in normal operation, but handle it
			d.currentZ = d.gridMinZ
			d.isMovingX = true
		} else {
			// Normal row transition: flip X direction
			// If we were going East (1), now go West (-1), and vice versa
			if d.direction > 0 {
				d.direction = -1 // Go West
			} else {
				d.direction = 1 // Go East
			}
			d.isMovingX = true
		}
	}
}

// SendPosition sends the current position to the server
func (d *MockDrone) SendPosition() error {
	if d.conn == nil || !d.isConnected {
		return fmt.Errorf("not connected")
	}

	azimuth := d.CalculateAzimuth()

	msg := SendPosition{
		Type:      MessageTypeSendPosition,
		DroneID:   d.droneID,
		Timestamp: time.Now().UnixNano(),
		X:         d.currentX,
		Y:         d.altitude,
		Z:         d.currentZ,
		Spherical: Spherical{
			Azimuth:    azimuth,
			Elevation:  -90,
			ScanRadius: 5,
			FOV:        60,
		},
		ETAMS: 200,
	}

	// Marshal and send through write channel
	data, err := json.Marshal(msg)
	if err != nil {
		return fmt.Errorf("failed to marshal position: %w", err)
	}

	select {
	case d.writeChan <- data:
		return nil
	default:
		return fmt.Errorf("write channel full")
	}
}

// PrintStatus prints beautiful console log of current drone status
func (d *MockDrone) PrintStatus() {
	azimuth := d.CalculateAzimuth()
	heading := d.getHeading(azimuth)

	// Create beautiful colored output
	fmt.Printf("\n")
	fmt.Printf("╔══════════════════════════════════════════════════════════════╗\n")
	fmt.Printf("║  🛸 DRONE STATUS                                               ║\n")
	fmt.Printf("╠══════════════════════════════════════════════════════════════╣\n")
	fmt.Printf("║  Drone ID:     %-45s║\n", d.droneID)
	fmt.Printf("║  Position:    (X: %6.1f, Y: %5.1f, Z: %6.1f)                 ║\n", d.currentX, d.altitude, d.currentZ)
	fmt.Printf("║  Altitude:    %-45.1f m║\n", d.altitude)
	fmt.Printf("║  Azimuth:     %-45.1f°║\n", azimuth)
	fmt.Printf("║  Heading:     %-45s║\n", heading)
	fmt.Printf("║  Pattern:     %-45s║\n", "Lawnmower Search")
	fmt.Printf("║  Tick Rate:   %-45s║\n", "200ms")
	fmt.Printf("║  Connected:   %-45v║\n", d.isConnected)
	fmt.Printf("╚══════════════════════════════════════════════════════════════╝\n")
}

// getHeading returns a human-readable heading based on azimuth
func (d *MockDrone) getHeading(azimuth float64) string {
	// Normalize azimuth to 0-360
	azimuth = math.Mod(azimuth+360, 360)

	switch {
	case azimuth >= 337.5 || azimuth < 22.5:
		return "NORTH (↑)"
	case azimuth >= 22.5 && azimuth < 67.5:
		return "NORTHEAST (↗)"
	case azimuth >= 67.5 && azimuth < 112.5:
		return "EAST (→)"
	case azimuth >= 112.5 && azimuth < 157.5:
		return "SOUTHEAST (↘)"
	case azimuth >= 157.5 && azimuth < 202.5:
		return "SOUTH (↓)"
	case azimuth >= 202.5 && azimuth < 247.5:
		return "SOUTHWEST (↙)"
	case azimuth >= 247.5 && azimuth < 292.5:
		return "WEST (←)"
	case azimuth >= 292.5 && azimuth < 337.5:
		return "NORTHWEST (↖)"
	default:
		return "UNKNOWN"
	}
}

// handleDisconnection handles the disconnection from the server
func (d *MockDrone) handleDisconnection(reason string) {
	if !d.isConnected {
		return
	}

	log.Printf("💔 Disconnected: %s", reason)
	d.isConnected = false

	// Close connection if open
	if d.conn != nil {
		d.conn.Close()
		d.conn = nil
	}
}

// reconnect attempts to reconnect with exponential backoff
func (d *MockDrone) reconnect() error {
	attempt := 0
	for {
		attempt++
		select {
		case <-d.stopChan:
			return fmt.Errorf("reconnection cancelled")
		default:
		}

		log.Printf("🔄 Attempting to reconnect (attempt %d, delay: %v)...", attempt, d.reconnectDelay)

		// Wait before attempting reconnection
		select {
		case <-d.stopChan:
			return fmt.Errorf("reconnection cancelled")
		case <-time.After(d.reconnectDelay):
		}

		// Try to connect
		err := d.Connect()
		if err == nil {
			// Successfully reconnected - reset delay and return
			log.Printf("🎉 Reconnected successfully after %d attempts", attempt)
			d.reconnectDelay = initialReconnectDelay
			return nil
		}

		log.Printf("❌ Reconnection failed: %v", err)

		// Check if we've exceeded max reconnect attempts
		if d.maxReconnectAttempts > 0 && attempt >= d.maxReconnectAttempts {
			return fmt.Errorf("max reconnection attempts (%d) exceeded", d.maxReconnectAttempts)
		}

		// Exponential backoff - double the delay
		d.reconnectDelay = time.Duration(math.Min(
			float64(d.reconnectDelay)*reconnectMultiplier,
			float64(maxReconnectDelay),
		))
		log.Printf("⏳ Next reconnection attempt in %v", d.reconnectDelay)
	}
}

// Run starts the drone simulation loop with automatic reconnection
func (d *MockDrone) Run() error {
	defer close(d.doneChan)

	log.SetOutput(os.Stdout)
	log.SetFlags(0)

	log.Println("╔══════════════════════════════════════════════════════════════╗")
	log.Println("║         🛸 MOCK DRONE WEBSOCKET CLIENT v2.0                    ║")
	log.Println("║         (With Auto-Reconnection & Keep-Alive)                 ║")
	log.Println("╚══════════════════════════════════════════════════════════════╝")

	// Initial connection
	for {
		err := d.Connect()
		if err == nil {
			break
		}
		log.Printf("❌ Initial connection failed: %v", err)
		log.Printf("⏳ Retrying in %v...", d.reconnectDelay)

		select {
		case <-d.stopChan:
			return fmt.Errorf("cancelled")
		case <-time.After(d.reconnectDelay):
		}

		// Exponential backoff for initial connection too
		d.reconnectDelay = time.Duration(math.Min(
			float64(d.reconnectDelay)*reconnectMultiplier,
			float64(maxReconnectDelay),
		))
	}

	// Main run loop
	for {
		// Send initial connection
		if err := d.SendInitConnection(); err != nil {
			log.Printf("❌ Failed to send init connection: %v", err)
			d.handleDisconnection("init connection failed")
			if err := d.reconnect(); err != nil {
				return fmt.Errorf("reconnection failed: %w", err)
			}
			continue
		}

		// Wait for grid snapshot
		if err := d.WaitForGridSnapshot(); err != nil {
			log.Printf("❌ Failed to receive grid snapshot: %v", err)
			d.handleDisconnection("grid snapshot failed")
			if err := d.reconnect(); err != nil {
				return fmt.Errorf("reconnection failed: %w", err)
			}
			continue
		}

		// Start tick loop
		log.Printf("🚀 Starting tick loop (interval: %v)", d.tickInterval)

		ticker := time.NewTicker(d.tickInterval)
		tickCount := 0

		for {
			select {
			case <-d.stopChan:
				ticker.Stop()
				log.Printf("🛑 Drone client stopped")
				return nil
			case <-ticker.C:
				tickCount++

				// Check if connected
				if !d.isConnected || d.conn == nil {
					log.Printf("⚠️  Connection lost during tick loop")
					ticker.Stop()
					goto Reconnect
				}

				// Update position based on lawnmower pattern
				d.UpdatePosition()

				// Send position to server
				if err := d.SendPosition(); err != nil {
					log.Printf("❌ Error sending position: %v", err)
					d.handleDisconnection("position send failed")
					ticker.Stop()
					goto Reconnect
				}

				// Print status every tick
				d.PrintStatus()

				// Log the position update
				azimuth := d.CalculateAzimuth()
				log.Printf("📍 Position update #%d: X=%.1f, Z=%.1f, Azimuth=%.1f°",
					tickCount, d.currentX, d.currentZ, azimuth)
			}
		}

	Reconnect:
		// Attempt to reconnect
		if err := d.reconnect(); err != nil {
			log.Printf("💥 Failed to reconnect: %v", err)
			return fmt.Errorf("reconnection failed: %w", err)
		}
		// Loop continues and reconnects successfully
	}
}

// Stop gracefully stops the drone client
func (d *MockDrone) Stop() {
	log.Printf("🛑 Stopping drone client...")
	close(d.stopChan)
	<-d.doneChan
	log.Printf("✅ Drone client stopped")
}

// formatJSON formats JSON bytes for pretty printing
func formatJSON(data []byte) string {
	var out bytes.Buffer
	if err := json.Indent(&out, data, "   ", ""); err != nil {
		return string(data)
	}
	return out.String()
}

// RunDroneClient is the entry point for the drone client
func RunDroneClient() {
	// Configure the lawnmower pattern
	config := LawnmowerConfig{
		GridMinX: 0.0,
		GridMaxX: 100.0,
		GridMinZ: 0.0,
		GridMaxZ: 100.0,
		StepSize: 2.0,
		MaxRows:  50,
	}

	// Create mock drone client
	drone := NewMockDrone("drone_1", config)

	// Handle graceful shutdown
	go func() {
		// In production, you could listen for OS signals here
		// For now, just let it run
		<-make(chan struct{})
	}()

	// Run the drone simulation
	if err := drone.Run(); err != nil {
		log.Fatalf("💥 Fatal error: %v", err)
	}
}
