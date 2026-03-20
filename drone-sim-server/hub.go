package main

import (
	"fmt"
	"log"
	"math"
	"math/rand"
	"net/http"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"github.com/lxzan/gws"
	"github.com/segmentio/encoding/json"
)

// Seed random number generator globally
func init() {
	rand.Seed(time.Now().UnixNano())
}

// =============================================================================
// Connection Configuration Constants
// =============================================================================

const (
	// DroneClient represents a drone connection
	DroneClient = "drone"
	// UIClient represents a UI/client connection
	UIClient = "ui"

	// Connection timing constants - Optimized for high-frequency drones
	ServerPingInterval = 5 * time.Second   // Ping interval (User requested 5-10s)
	ServerReadDeadline = 15 * time.Second  // Read deadline
	ServerWriteDeadline = 5 * time.Second  // Write deadline

	// Connection health monitoring
	HealthCheckInterval = 5 * time.Second  // How often to check connection health
	MaxMissedPings      = 2                // Max missed pings before considering connection dead
	ConnectionTimeout   = 10 * time.Second // Max time to establish initial connection

	// Channel buffer sizes for backpressure
	ClientSendBufferSize    = 256 // Buffer for outbound messages
	ClientReceiveBufferSize = 256 // Buffer for inbound messages
	HubChannelBufferSize    = 256 // Buffer for hub routing channels
)

// =============================================================================
// Command Base Constants - Where drones spawn
// =============================================================================

const (
	BaseX = 0.0
	BaseY = 40.0
)

// =============================================================================
// DroneState - Thread-safe drone state management
// =============================================================================

// DroneState represents the state of a connected drone
type DroneState struct {
	ID        string    `json:"drone_id"`
	X         float64   `json:"x"`
	Y         float64   `json:"y"`
	Z         float64   `json:"z"`
	Timestamp time.Time `json:"timestamp"`
}

// Global Drone Map - thread-safe (acceptable for state storage)
var (
	Drones     = make(map[string]*DroneState)
	DroneMutex sync.RWMutex
)

// =============================================================================
// Survivor State - Server-managed survivor positions
// =============================================================================

// Survivor represents a survivor position in the disaster area
type Survivor struct {
	ID      string  `json:"id"`
	X       float64 `json:"x"`
	Y       float64 `json:"y"`       // Altitude in Three.js (ground = 0)
	Z       float64 `json:"z"`       // Ground plane coordinate
	Status  string  `json:"status"`
	Thermal float64 `json:"thermal"` // Body temperature in °C (36–37.5), used by /scan
}

// Global Survivors - randomly generated on server startup
var (
	Survivors     []Survivor
	SurvivorsMutex sync.RWMutex
)

// GenerateSurvivors creates random survivors across the map area
// Map area: X: -40 to 40, Z: -40 to 40
func GenerateSurvivors(count int) []Survivor {
	survivors := make([]Survivor, count)
	
	for i := 0; i < count; i++ {
		// Random position within map bounds (avoiding command base at 0,0)
		var x, z float64
		for {
			x = (rand.Float64()*80 - 40) // -40 to 40
			z = (rand.Float64()*80 - 40) // -40 to 40
			// Avoid spawning too close to command base (within 10 units)
			distFromBase := math.Sqrt(x*x + z*z)
			if distFromBase > 10 {
				break
			}
		}
		
		survivors[i] = Survivor{
			ID:      fmt.Sprintf("survivor_%d", i+1),
			X:       x,
			Y:       0,                           // Ground level (maps to Three.js Y)
			Z:       z,                           // Ground plane (maps to Three.js Z)
			Status:  "DETECTED",
			Thermal: 36.0 + rand.Float64()*1.5,  // 36.0–37.5 °C body temp
		}
		
		log.Printf("🚑 Generated survivor %d at (%.1f, %.1f)", i+1, x, z)
	}
	
	return survivors
}

// GetSurvivors returns a copy of the current survivors list
func GetSurvivors() []Survivor {
	return Survivors
}

// =============================================================================
// Building State - Server-managed building positions
// =============================================================================

// Building represents an uncorrupted building obstacle in the disaster area
type Building struct {
	ID      string  `json:"id"`
	X       float64 `json:"x"`       // Grid X (maps to Three.js X)
	Y       float64 `json:"y"`       // Grid Z/ground plane (maps to Three.js Z)
	Width   float64 `json:"width"`   // X dimension
	Height  float64 `json:"height"`  // Vertical dimension (Three.js Y)
	Depth   float64 `json:"depth"`   // Z dimension
	Thermal float64 `json:"thermal"` // Surface temperature °C (14–18)
}

// Global Buildings - randomly generated on server startup
var (
	Buildings      []Building
	BuildingsMutex sync.RWMutex
)

// OccupancyGrid maps each grid cell to the tallest building height above it.
// Pre-built once after GenerateBuildings so bresenhamLOS can do O(1) lookups.
var (
	OccupancyGrid      map[[2]int]float64
	OccupancyGridMutex sync.RWMutex
)

// GenerateBuildings creates buildings scattered across the map, avoiding the command base
func GenerateBuildings(count int) []Building {
	buildings := make([]Building, count)
	for i := 0; i < count; i++ {
		w := float64(4 + rand.Intn(6)) // width  4–9
		h := float64(3 + rand.Intn(8)) // height 3–10
		d := float64(4 + rand.Intn(6)) // depth  4–9
		var bx, by float64
		for {
			bx = float64(rand.Intn(60) - 30) // -30 to 30
			by = float64(rand.Intn(60) - 30) // -30 to 30
			if math.Sqrt(bx*bx+by*by) > 12 {
				break
			}
		}
		buildings[i] = Building{
			ID:      fmt.Sprintf("building_%d", i+1),
			X:       bx,
			Y:       by,
			Width:   w,
			Height:  h,
			Depth:   d,
			Thermal: 14 + rand.Float64()*4,
		}
		log.Printf("🏢 Generated building %d at (%.1f, %.1f) size %.0fx%.0fx%.0f", i+1, bx, by, w, h, d)
	}
	return buildings
}

// buildOccupancyGrid pre-computes a height map from all building footprints.
// Each cell stores the tallest building above it so bresenhamLOS can check
// droneZ > cellHeight in O(1) without iterating buildings per ray step.
func buildOccupancyGrid() {
	grid := make(map[[2]int]float64)
	BuildingsMutex.RLock()
	for _, b := range Buildings {
		halfW := b.Width / 2
		halfD := b.Depth / 2
		for ix := int(b.X - halfW); ix <= int(b.X+halfW); ix++ {
			for iy := int(b.Y - halfD); iy <= int(b.Y+halfD); iy++ {
				cell := [2]int{ix, iy}
				if grid[cell] < b.Height {
					grid[cell] = b.Height
				}
			}
		}
	}
	BuildingsMutex.RUnlock()
	OccupancyGridMutex.Lock()
	OccupancyGrid = grid
	OccupancyGridMutex.Unlock()
	log.Printf("🗺️  Occupancy grid built: %d occupied cell(s)", len(grid))
}

// GetBuildingBlockedCells expands each building footprint into individual grid cells
// for the drone's A* pathfinding to treat as impassable
func GetBuildingBlockedCells() []BlockedArea {
	var cells []BlockedArea
	BuildingsMutex.RLock()
	defer BuildingsMutex.RUnlock()
	for _, b := range Buildings {
		halfW := b.Width / 2
		halfD := b.Depth / 2
		for ix := int(b.X - halfW); ix <= int(b.X+halfW); ix++ {
			for iy := int(b.Y - halfD); iy <= int(b.Y+halfD); iy++ {
				cells = append(cells, BlockedArea{X: float64(ix), Y: float64(iy), Radius: 0})
			}
		}
	}
	return cells
}


// =============================================================================
// Client Struct - Queue-based architecture
// =============================================================================

// bufferPool minimizes GC pauses for high-frequency telemetry
var bufferPool = sync.Pool{
	New: func() any {
		// Default to 4KB buffers
		b := make([]byte, 0, 4096)
		return &b
	},
}

// =============================================================================
// Client Struct - Non-Blocking Send Channel
// =============================================================================

// Client represents a WebSocket connection in the hub
type Client struct {
	// Hub is the pointer to the Hub that manages this client
	Hub *Hub
	// Conn is the gws WebSocket connection
	Conn *gws.Conn
	// Send is a buffered channel for outgoing messages (Zero-Pressure)
	Send chan []byte
	// ClientType is either "drone" or "ui"
	ClientType string
	// DroneID is the unique identifier for drone clients (empty for UI)
	DroneID string

	// quit channel for graceful shutdown
	quit chan struct{}
}

// =============================================================================
// Hub Struct - Queue-based routing architecture
// =============================================================================

// Hub maintains the set of active clients and routes messages through channels
// Uses pure channel-based communication - no mutex locks on client maps
type Hub struct {
	// Client registration/unregistration via channels
	Register   chan *Client
	Unregister chan *Client

	// Broadcast channel for messages to all UI clients
	Broadcast chan []byte

	// Dedicated routing channels
	DroneMessages chan []byte
	UIMessages    chan []byte

	// Statistics and Reliability
	droppedPackets uint64

	// Internal state tracking
	mu sync.RWMutex
	// DroneClients map
	DroneClients map[*Client]bool
	// UIClients map
	UIClients map[*Client]bool

	// Last known send_position message per drone
	lastPositionMsg map[string][]byte
}

// =============================================================================
// Hub Methods - Pure queue-based implementation
// =============================================================================

// NewHub creates and returns a new Hub instance
func NewHub() *Hub {
	return &Hub{
		Register:        make(chan *Client),
		Unregister:      make(chan *Client),
		Broadcast:       make(chan []byte, HubChannelBufferSize),
		DroneMessages:   make(chan []byte, HubChannelBufferSize),
		UIMessages:      make(chan []byte, HubChannelBufferSize),
		DroneClients:    make(map[*Client]bool),
		UIClients:       make(map[*Client]bool),
		lastPositionMsg: make(map[string][]byte),
	}
}

// =============================================================================
// gws.EventHandler Implementation
// =============================================================================

func (h *Hub) OnOpen(c *gws.Conn) {
	// Handled in ServeWs
}

func (h *Hub) OnClose(c *gws.Conn, err error) {
	if val, ok := c.Session().Load("client"); ok {
		if client, ok := val.(*Client); ok {
			h.Unregister <- client
		}
	}
}

func (h *Hub) OnPing(c *gws.Conn, payload []byte) {
	_ = c.WritePong(payload)
}

func (h *Hub) OnPong(c *gws.Conn, payload []byte) {
	// gws handles read deadlines internally based on activity
}

func (h *Hub) OnMessage(c *gws.Conn, message *gws.Message) {
	defer message.Close()
	val, ok := c.Session().Load("client")
	if !ok {
		return
	}
	client, ok := val.(*Client)
	if !ok {
		return
	}

	// Zero-copy byte slice (valid until message.Close() which is deferred)
	data := message.Bytes()
	
	// Create a stable copy for the hub channels if needed
	// Hub channels are buffered, so we usually don't need a copy if processed immediately
	// but since we have multiple consumers potentially, let's copy.
	msgCopy := make([]byte, len(data))
	copy(msgCopy, data)

	if client.ClientType == DroneClient {
		select {
		case h.DroneMessages <- msgCopy:
		default:
			atomic.AddUint64(&h.droppedPackets, 1)
		}
	} else {
		select {
		case h.UIMessages <- msgCopy:
		default:
			atomic.AddUint64(&h.droppedPackets, 1)
		}
	}
}

// Run is the main hub goroutine that handles all events via channels
// This is the central message router - all client communication flows through here
func (h *Hub) Run() {
	// Create ticker for periodic grid snapshots (e.g., every 5 seconds)
	// This helps clients stay in sync even if updates are dropped.
	snapshotTicker := time.NewTicker(5 * time.Second)
	defer snapshotTicker.Stop()

	for {
		select {
		case client := <-h.Register:
			h.registerClient(client)

		case client := <-h.Unregister:
			h.unregisterClient(client)

		case message := <-h.Broadcast:
			// Regular broadcast to all UI clients
			h.broadcastToUIClients(message)

		case message := <-h.DroneMessages:
			h.handleDroneMessage(message)

		case message := <-h.UIMessages:
			h.handleUIMessage(message)

		case <-snapshotTicker.C:
			h.broadcastGridSnapshot()
		}
	}
}

// broadcastGridSnapshot sends a full state sync to all UI clients
func (h *Hub) broadcastGridSnapshot() {
	snapshot := h.GetInitialGridSnapshot()
	snapshot.Timestamp = time.Now().UnixMilli()

	if data, err := json.Marshal(snapshot); err == nil {
		h.broadcastToUIClients(data)
	}
}

// registerClient adds a client and starts its listener goroutine
// Uses channel-based routing - no mutex locks
func (h *Hub) registerClient(client *Client) {
	// Initialize non-blocking send channel
	client.Send = make(chan []byte, ClientSendBufferSize)
	client.quit = make(chan struct{})

	switch client.ClientType {
	case DroneClient:
		h.mu.Lock()
		h.DroneClients[client] = true
		h.mu.Unlock()
		log.Printf("📡 Drone client registered: %s", client.DroneID)

	case UIClient:
		h.mu.Lock()
		h.UIClients[client] = true
		// Snapshot cached positions
		cachedPositions := make([][]byte, 0, len(h.lastPositionMsg))
		for _, msg := range h.lastPositionMsg {
			cachedPositions = append(cachedPositions, msg)
		}
		h.mu.Unlock()
		log.Printf("🖥️  UI client registered")

		// Replay last known drone positions
		for _, msg := range cachedPositions {
			select {
			case client.Send <- msg:
			default:
			}
		}

	default:
		log.Printf("⚠️  Unknown client type: %s", client.ClientType)
	}
}

// unregisterClient removes a client and cleans up.
// Safe to call multiple times — only the first call for a given client
// does real work; subsequent calls are no-ops (client already removed from map).
func (h *Hub) unregisterClient(client *Client) {
	switch client.ClientType {
	case DroneClient:
		h.mu.Lock()
		if _, ok := h.DroneClients[client]; ok {
			delete(h.DroneClients, client)
			h.mu.Unlock()

			// Signal pumps to stop, then close data channels.
			// Done inside the existence-check so we never close twice.
			close(client.quit)
			close(client.Send)

			// Remove from global drone state
			DroneMutex.Lock()
			delete(Drones, client.DroneID)
			DroneMutex.Unlock()

			log.Printf("🛑 Drone client unregistered: %s", client.DroneID)
		} else {
			h.mu.Unlock()
			// Already unregistered — ignore duplicate call
		}

	case UIClient:
		h.mu.Lock()
		if _, ok := h.UIClients[client]; ok {
			delete(h.UIClients, client)
			h.mu.Unlock()

			// Signal pumps to stop, then close data channels.
			close(client.quit)
			close(client.Send)

			log.Printf("🖥️  UI client unregistered")
		} else {
			h.mu.Unlock()
		}
	}
}


// handleDroneMessage processes messages from drones (send_position, survivor_detected)
func (h *Hub) handleDroneMessage(message []byte) {
	var msgType struct {
		Type string `json:"type"`
	}

	if err := json.Unmarshal(message, &msgType); err != nil {
		log.Printf("⚠️  Error parsing drone message: %v", err)
		return
	}

	switch msgType.Type {
	case MessageTypeSendPosition:
		// Parse position data, update state, and broadcast with SeqNum
		h.handleSendPosition(message)

	case MessageTypeSurvivorDetected:
		// Parse survivor detection from drone
		h.handleSurvivorDetected(message)
		// Broadcast to UI clients
		h.broadcastToUIClients(message)

	case MessageTypeScanHeatmap:
		// Raw thermal readings from drone scan — forward to UI for heatmap rendering
		h.broadcastToUIClients(message)

	default:
		// Forward other drone messages to UI
		h.broadcastToUIClients(message)
	}
}

// handleSendPosition updates the DroneState map with the drone's current position
func (h *Hub) handleSendPosition(message []byte) {
	var posMsg SendPosition

	if err := json.Unmarshal(message, &posMsg); err != nil {
		log.Printf("⚠️  Error parsing position message: %v", err)
		return
	}

	// Update drone state with thread-safe access
	DroneMutex.Lock()
	Drones[posMsg.DroneID] = &DroneState{
		ID:        posMsg.DroneID,
		X:         posMsg.X,
		Y:         posMsg.Y,
		Z:         posMsg.Z,
		Timestamp: time.UnixMilli(posMsg.Timestamp),
	}
	DroneMutex.Unlock()

	// Cache for replay to future UI clients
	h.cacheDronePosition(message)
	// Broadcast to UI clients
	h.broadcastToUIClients(message)

	log.Printf("📍 Drone %s position updated: (%.2f, %.2f, %.2f)", 
		posMsg.DroneID, posMsg.X, posMsg.Y, posMsg.Z)
}

// cacheDronePosition stores the latest send_position message per drone ID
// so new UI clients get current drone state on connect
func (h *Hub) cacheDronePosition(message []byte) {
	var msg struct {
		DroneID string `json:"drone_id"`
	}
	if err := json.Unmarshal(message, &msg); err != nil || msg.DroneID == "" {
		return
	}
	h.mu.Lock()
	h.lastPositionMsg[msg.DroneID] = message
	h.mu.Unlock()
}

// handleSurvivorDetected logs and processes survivor detection events
func (h *Hub) handleSurvivorDetected(message []byte) {
	var detectMsg SurvivorDetected

	if err := json.Unmarshal(message, &detectMsg); err != nil {
		log.Printf("⚠️  Error parsing survivor_detected message: %v", err)
		return
	}

	log.Printf("🚨 Survivor detected by drone %s at (%.2f, %.2f, %.2f) - confidence: %.2f",
		detectMsg.DroneID, detectMsg.X, detectMsg.Y, detectMsg.Z, detectMsg.Confidence)
}

// handleUIMessage processes messages from UI clients
func (h *Hub) handleUIMessage(message []byte) {
	var msgType struct {
		Type string `json:"type"`
	}

	if err := json.Unmarshal(message, &msgType); err != nil {
		log.Printf("⚠️  Error parsing UI message: %v", err)
		return
	}

	switch msgType.Type {
	case MessageTypeSurvivorDetected:
		// UI sends survivor_detected event - route to specific drone
		h.handleUISurvivorDetected(message)
		// Broadcast acknowledgment to all UI clients
		h.broadcastToUIClients(message)

	default:
		log.Printf("📥 Received unknown UI message type: %s", msgType.Type)
	}
}

// handleUISurvivorDetected routes survivor_detected from UI to the appropriate drone
func (h *Hub) handleUISurvivorDetected(message []byte) {
	var detectMsg struct {
		Type      string `json:"type"`
		DroneID   string `json:"drone_id"`
		TargetID  string `json:"target_id"`
		Timestamp int64  `json:"timestamp"`
	}

	if err := json.Unmarshal(message, &detectMsg); err != nil {
		log.Printf("⚠️  Error parsing UI survivor_detected message: %v", err)
		return
	}

	log.Printf("🎯 UI survivor_detected: target %s assigned to drone %s", detectMsg.TargetID, detectMsg.DroneID)

	// Route to specific drone if connected - use channel-based routing
	h.mu.RLock()
	defer h.mu.RUnlock()

	for client := range h.DroneClients {
		if client.DroneID == detectMsg.DroneID {
			select {
			case client.Send <- message:
				log.Printf("📤 Routed survivor_detected to drone %s", detectMsg.DroneID)
			default:
				log.Printf("⚠️  Failed to route to drone %s (channel full)", detectMsg.DroneID)
			}
			return
		}
	}

	log.Printf("⚠️  Drone %s not connected, could not route survivor_detected", detectMsg.DroneID)
}

// BroadcastToUI sends a message to all connected UI clients
func (h *Hub) BroadcastToUI(message []byte) {
	select {
	case h.Broadcast <- message:
	default:
		atomic.AddUint64(&h.droppedPackets, 1)
	}
}

// BroadcastToDrones sends a message to all connected drone clients (Zero-Pressure)
func (h *Hub) BroadcastToDrones(message []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for client := range h.DroneClients {
		select {
		case client.Send <- message:
		default:
			// Discard message to prevent backpressure
			atomic.AddUint64(&h.droppedPackets, 1)
		}
	}
}

// broadcastToUIClients sends to all UI clients (Zero-Pressure)
func (h *Hub) broadcastToUIClients(message []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for client := range h.UIClients {
		select {
		case client.Send <- message: 
		default:
			// Discard message to prevent backpressure
			atomic.AddUint64(&h.droppedPackets, 1)
		}
	}
}

// getDroneCount returns the current number of connected drone clients
func (h *Hub) getDroneCount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.DroneClients)
}

// getUICount returns the current number of connected UI clients
func (h *Hub) getUICount() int {
	h.mu.RLock()
	defer h.mu.RUnlock()
	return len(h.UIClients)
}

// GetInitialGridSnapshot returns the initial grid snapshot with Command Base coordinates
func (h *Hub) GetInitialGridSnapshot() GridSnapshot {
	return GridSnapshot{
		Type:      MessageTypeGridSnapshot,
		Timestamp: time.Now().UnixMilli(),
		Blocked: []BlockedArea{
			{X: 10, Y: 10, Radius: 5},
			{X: 25, Y: 30, Radius: 8},
			{X: 50, Y: 20, Radius: 6},
		},
		CommandBase: &CommandBase{
			X: BaseX,
			Y: BaseY,
		},
	}
}

// =============================================================================
// Client Methods - ReadPump and WritePump (Queue-based)
// =============================================================================

// =============================================================================
// Thermal Scan — shared computation + HTTP handler + passive scanner
// =============================================================================

const DefaultScanRadius = 5.0 // grid cells; used as fallback when /scan is called without a radius

// ThermalReading is a single raw thermal data point.
// Drone interprets: 30–42 °C = likely human, 14–26 °C = building/background.
type ThermalReading struct {
	X           float64 `json:"x"`
	Y           float64 `json:"y"`
	TempCelsius float64 `json:"temp_celsius"`
}

// bresenhamLOS walks grid cells from (x1,y1) to (x2,y2) using Bresenham's line
// algorithm. Returns true if line of sight is clear — no building cell in the path
// is taller than droneZ. The start cell (drone position) is skipped.
func bresenhamLOS(x1, y1, x2, y2 int, droneZ float64) bool {
	dx := x2 - x1
	if dx < 0 {
		dx = -dx
	}
	dy := y2 - y1
	if dy < 0 {
		dy = -dy
	}
	sx, sy := 1, 1
	if x1 > x2 {
		sx = -1
	}
	if y1 > y2 {
		sy = -1
	}
	err := dx - dy
	x, y := x1, y1

	OccupancyGridMutex.RLock()
	defer OccupancyGridMutex.RUnlock()

	for {
		if x == x2 && y == y2 {
			return true // reached target — clear
		}
		if !(x == x1 && y == y1) { // skip drone's own cell
			if h := OccupancyGrid[[2]int{x, y}]; h > droneZ {
				return false // building taller than drone altitude blocks LOS
			}
		}
		e2 := 2 * err
		if e2 > -dy {
			err -= dy
			x += sx
		}
		if e2 < dx {
			err += dx
			y += sy
		}
	}
}

// in3DCone checks whether target (tx, ty, tz) falls inside the drone's 3D FOV cone.
// azimuth: horizontal direction degrees, atan2(dx,-dy) convention (0=south, 90=east).
// elevation: vertical tilt degrees (-90=straight down, 0=horizon, positive=up).
// fov: full cone angle in degrees. fov>=360 always passes (full-circle passive scan).
// Roll is not needed — a circular cone is symmetric around its axis.
func in3DCone(droneX, droneY, droneZ, tx, ty, tz, azimuth, elevation, fov float64) bool {
	if fov >= 360 {
		return true
	}
	azRad := azimuth * math.Pi / 180
	elRad := elevation * math.Pi / 180
	// Camera direction unit vector
	camX := math.Sin(azRad) * math.Cos(elRad)
	camY := -math.Cos(azRad) * math.Cos(elRad)
	camZ := math.Sin(elRad) // negative for downward elevation
	// Vector from drone to target
	dx := tx - droneX
	dy := ty - droneY
	dz := tz - droneZ
	dist := math.Sqrt(dx*dx + dy*dy + dz*dz)
	if dist == 0 {
		return true
	}
	dot := (dx*camX + dy*camY + dz*camZ) / dist
	if dot > 1 {
		dot = 1
	}
	if dot < -1 {
		dot = -1
	}
	return math.Acos(dot)*180/math.Pi <= fov/2
}

// computeThermalReadings returns thermal readings visible from the drone's position.
//
// Three realism layers:
//   1. FOV cone   — only targets inside azimuth±fov/2 are considered (inCone).
//   2. LOS check  — Bresenham ray from drone to target; blocked if a building cell
//                   is taller than droneZ (drone can see over buildings it flies above).
//   3. 3D falloff — dist3D = sqrt(dx²+dy²+dz²); angle_factor = dz/dist3D so the
//                   signal is strongest directly above the target and weakens at shallow
//                   angles (matches a downward-pointing thermal camera).
//
// Altitude-scaled radius (passive cone scans only, fov < 360):
//   ground_radius = droneZ × tan(fov/2) — the camera's actual ground footprint.
//   effective_radius = min(commanded_radius, ground_radius).
func computeThermalReadings(droneX, droneY, droneZ, scanRadius, azimuth, elevation, fov float64) []ThermalReading {

	readings := []ThermalReading{}
	droneXi := int(math.Round(droneX))
	droneYi := int(math.Round(droneY))

	// When the camera is tilted forward (elevation < 0), the footprint center is
	// `droneZ / tan(-elevation)` units ahead horizontally. Extend the 2D radius to
	// cover the full visible ground area; otherwise survivors in view are missed.
	effectiveRadius := scanRadius
	if elevation < 0 && droneZ > 0 {
		elRad := elevation * math.Pi / 180
		tanVal := math.Tan(-elRad)
		if tanVal > 0.01 { // guard against near-horizontal cameras (huge reach)
			forwardReach := droneZ / tanVal
			if forwardReach > effectiveRadius {
				effectiveRadius = forwardReach + scanRadius
			}
		}
	}

	SurvivorsMutex.RLock()
	for _, s := range Survivors {
		dx := s.X - droneX
		dy := s.Z - droneY // Survivor.Z is the ground plane coordinate
		dist2D := math.Sqrt(dx*dx + dy*dy)
		if dist2D > effectiveRadius {
			continue
		}
		if !in3DCone(droneX, droneY, droneZ, s.X, s.Z, 0, azimuth, elevation, fov) {
			continue
		}
		if !bresenhamLOS(droneXi, droneYi, int(math.Round(s.X)), int(math.Round(s.Z)), droneZ) {
			continue // building blocks line of sight
		}
		// 3D falloff + angle of incidence (strongest signal directly above)
		dist3D := math.Sqrt(dx*dx + dy*dy + droneZ*droneZ)
		angleFactor := 1.0
		if dist3D > 0 {
			angleFactor = droneZ / dist3D
		}
		apparent := s.Thermal * math.Exp(-dist3D*0.005) * angleFactor
		noise := (rand.Float64() - 0.5) * 0.4
		temp := math.Round((apparent+noise)*10) / 10
		readings = append(readings, ThermalReading{X: s.X, Y: s.Z, TempCelsius: temp})
	}
	SurvivorsMutex.RUnlock()

	BuildingsMutex.RLock()
	for _, b := range Buildings {
		dx := b.X - droneX
		dy := b.Y - droneY
		dist2D := math.Sqrt(dx*dx + dy*dy)
		if dist2D <= 0 || dist2D > effectiveRadius {
			continue
		}
		if !in3DCone(droneX, droneY, droneZ, b.X, b.Y, 0, azimuth, elevation, fov) {
			continue
		}
		// Buildings: skip LOS check when drone is above the building
		if droneZ <= b.Height {
			if !bresenhamLOS(droneXi, droneYi, int(math.Round(b.X)), int(math.Round(b.Y)), droneZ) {
				continue
			}
		}
		dist3D := math.Sqrt(dx*dx + dy*dy + droneZ*droneZ)
		angleFactor := 1.0
		if dist3D > 0 {
			angleFactor = droneZ / dist3D
		}
		apparent := b.Thermal * math.Exp(-dist3D*0.3) * angleFactor
		noise := (rand.Float64() - 0.5) * 0.3
		temp := math.Round((apparent+noise)*10) / 10
		readings = append(readings, ThermalReading{X: b.X, Y: b.Y, TempCelsius: temp})
	}
	BuildingsMutex.RUnlock()

	return readings
}

// ScanHandler handles GET /scan?x=&y=&z=&radius=
// Active scan called by the drone's thermal_scan function via HTTP.
func ScanHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")

	q := r.URL.Query()
	droneX, _ := strconv.ParseFloat(q.Get("x"), 64)
	droneY, _ := strconv.ParseFloat(q.Get("y"), 64)
	droneZ, _ := strconv.ParseFloat(q.Get("z"), 64)
	scanRadius, _ := strconv.ParseFloat(q.Get("radius"), 64)
	azimuth, _ := strconv.ParseFloat(q.Get("azimuth"), 64)
	fov, _ := strconv.ParseFloat(q.Get("fov"), 64)
	elevation, _ := strconv.ParseFloat(q.Get("elevation"), 64)
	if scanRadius <= 0 {
		scanRadius = DefaultScanRadius
	}
	if fov <= 0 {
		fov = 360 // no fov param = full-circle active scan
	}
	if q.Get("elevation") == "" {
		elevation = -90.0 // default straight down for backward compatibility
	}

	readings := computeThermalReadings(droneX, droneY, droneZ, scanRadius, azimuth, elevation, fov)
	json.NewEncoder(w).Encode(readings)
}

// MapInfoHandler handles GET /map-info
// Returns the searchable coordinate bounds so the LLM agent does not need
// to hard-code map dimensions in its system prompt.
func MapInfoHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"x_min":    -40,
		"x_max":    40,
		"y_min":    -40,
		"y_max":    40,
		"base_x":   BaseX,
		"base_y":   BaseY,
		"note":     "Drone coordinates: x horizontal, y horizontal, z altitude. Base is at (0,0).",
	})
}

// upgrader configures the gws upgrader
var upgrader = gws.NewUpgrader(&Hub{}, &gws.ServerOption{
	ReadMaxPayloadSize: 512 * 1024, // 512KB
	Authorize: func(r *http.Request, session gws.SessionStorage) bool {
		return true
	},
})

// WritePump writes messages from the Send channel to the gws connection
// Includes ping handling and graceful shutdown
func (c *Client) WritePump() {
	ticker := time.NewTicker(ServerPingInterval)
	defer func() {
		ticker.Stop()
		c.Conn.NetConn().Close()
	}()

	for {
		select {
		case message, ok := <-c.Send:
			if !ok {
				_ = c.Conn.WriteMessage(gws.OpcodeCloseConnection, nil)
				return
			}
			// Optimized write
			if err := c.Conn.WriteMessage(gws.OpcodeText, message); err != nil {
				return
			}

		case <-ticker.C:
			// Send ping to keep connection alive
			if err := c.Conn.WritePing(nil); err != nil {
				return
			}

		case <-c.quit:
			return
		}
	}
}

// getClientIdentifier returns a string identifier for logging
func (c *Client) getClientIdentifier() string {
	if c.DroneID != "" {
		return fmt.Sprintf("drone[%s]", c.DroneID)
	}
	return "ui-client"
}

// ServeWs upgrades the HTTP connection to WebSocket and registers the client
func ServeWs(hub *Hub, w http.ResponseWriter, r *http.Request, clientType string) {
	// Extract drone ID if this is a drone client
	droneID := ""
	if clientType == DroneClient {
		droneID = r.URL.Query().Get("drone_id")
		if droneID == "" {
			droneID = generateDroneID()
		}
	}

	// Upgrade HTTP to WebSocket using gws
	conn, err := gws.NewUpgrader(hub, &gws.ServerOption{
		ReadMaxPayloadSize: 512 * 1024, // 512KB
		Authorize:          func(r *http.Request, session gws.SessionStorage) bool { return true },
	}).Upgrade(w, r)
	if err != nil {
		log.Printf("WebSocket upgrade error: %v", err)
		return
	}

	client := &Client{
		Hub:        hub,
		Conn:       conn,
		ClientType: clientType,
		DroneID:    droneID,
		quit:       make(chan struct{}),
	}

	// Store client in session for OnMessage/OnClose
	conn.Session().Store("client", client)

	// Register client with hub
	hub.Register <- client

	// Start write pump
	go client.WritePump()

	// Send initial connection response
	allBlocked := GetBuildingBlockedCells()
	initialResponse := InitConnectionResponse{
		Type:      MessageTypeInitConnection,
		DroneID:   droneID,
		Timestamp: time.Now().UnixMilli(),
		GridSnapshot: GridSnapshot{
			Type:      MessageTypeGridSnapshot,
			Timestamp: time.Now().UnixMilli(),
			Blocked:   allBlocked,
			CommandBase: &CommandBase{
				X: BaseX,
				Y: BaseY,
			},
		},
		Position: Position{
			X: BaseX,
			Y: BaseY,
			Z: 10.0,
		},
		Survivors: func() []Survivor {
			SurvivorsMutex.RLock()
			defer SurvivorsMutex.RUnlock()
			list := make([]Survivor, len(Survivors))
			for i, s := range Survivors {
				list[i] = s
				list[i].Status = "UNDETECTED"
			}
			return list
		}(),
		Buildings: Buildings,
	}

	if responseJSON, err := json.Marshal(initialResponse); err == nil {
		select {
		case client.Send <- responseJSON:
		default:
		}
	}

	if clientType == DroneClient {
		droneGrid := map[string]interface{}{
			"intention": "grid_snapshot",
			"timestamp": time.Now().UnixMilli(),
			"blocked":   allBlocked,
		}
		if droneGridJSON, err2 := json.Marshal(droneGrid); err2 == nil {
			select {
			case client.Send <- droneGridJSON:
			default:
			}
		}
	}

	// Block here and read from connection
	conn.ReadLoop()
}

// generateDroneID generates a unique drone ID
func generateDroneID() string {
	return fmt.Sprintf("drone-%s-%04d", time.Now().Format("20060102150405"), rand.Intn(10000))
}

// =============================================================================
// Additional Types
// =============================================================================

// InitConnectionResponse is sent to clients upon successful connection
type InitConnectionResponse struct {
	Type         string      `json:"type"`
	DroneID      string      `json:"drone_id,omitempty"`
	Timestamp    int64       `json:"timestamp"`
	GridSnapshot GridSnapshot `json:"grid_snapshot"`
	Position     Position    `json:"position,omitempty"`
	Survivors    []Survivor  `json:"survivors,omitempty"`
	Buildings    []Building  `json:"buildings,omitempty"`
}
