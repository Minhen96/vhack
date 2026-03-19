package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"math/rand"
	"net"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/gorilla/websocket"
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

	// Connection timing constants - tuned for stability
	// Read deadline should be longer than ping interval to allow for network latency
	ServerPingInterval = 25 * time.Second  // Ping interval
	ServerReadDeadline = 60 * time.Second  // Read deadline (longer for reconnection resilience)
	ServerWriteDeadline = 10 * time.Second // Write deadline for messages

	// Connection health monitoring
	HealthCheckInterval = 10 * time.Second // How often to check connection health
	MaxMissedPings      = 3                 // Max missed pings before considering connection dead
	ConnectionTimeout   = 30 * time.Second // Max time to establish initial connection

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
	BaseY = 50.0
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

// Client represents a WebSocket connection in the hub
// Uses dedicated channels for send/receive to eliminate mutex locks
type Client struct {
	// Hub is the pointer to the Hub that manages this client
	Hub *Hub
	// Conn is the WebSocket connection
	Conn *websocket.Conn
	// Send is a buffered channel for outgoing messages (write queue)
	// WritePump is the only goroutine that reads from this channel
	Send chan []byte
	// Receive is a buffered channel for incoming messages (read queue)
	// ReadPump writes to this channel, Hub's listener reads from it
	Receive chan []byte
	// ClientType is either "drone" or "ui"
	ClientType string
	// DroneID is the unique identifier for drone clients (empty for UI)
	DroneID string

	// Connection health tracking
	lastPingTime      time.Time     // Last time we received a ping/activity
	missedPings       int           // Number of missed pings
	isHealthy         bool          // Connection health status
	healthCheckTicker *time.Ticker  // Health check ticker
	wg                sync.WaitGroup // WaitGroup for graceful shutdown

	// quit channel for graceful shutdown
	quit chan struct{}
}

// =============================================================================
// Hub Struct - Queue-based routing architecture
// =============================================================================

// Hub maintains the set of active clients and routes messages through channels
// Uses pure channel-based communication - no mutex locks on client maps
type Hub struct {
	// Client registration/unregistration via channels (no mutex needed)
	Register   chan *Client
	Unregister chan *Client

	// Broadcast channel for messages to all UI clients
	Broadcast chan []byte

	// Dedicated routing channels (channel-based message bus)
	// DroneMessages: messages from drones to be routed to UI
	DroneMessages chan []byte
	// UIMessages: messages from UI to be routed to drones
	UIMessages chan []byte

	// DroneState mutex for thread-safe access to drone state (acceptable)
	DroneState sync.RWMutex

	// Connection statistics
	totalConnections    int64
	totalDisconnections int64

	// Internal state tracking (protected by mutex for stats only)
	mu sync.RWMutex
	// DroneClients map for stats and iteration (read-only, updated via channels)
	DroneClients map[*Client]bool
	// UIClients map for stats and iteration (read-only, updated via channels)
	UIClients map[*Client]bool
}

// =============================================================================
// Hub Methods - Pure queue-based implementation
// =============================================================================

// NewHub creates and returns a new Hub instance with channel-based architecture
func NewHub() *Hub {
	return &Hub{
		Register:       make(chan *Client),
		Unregister:     make(chan *Client),
		Broadcast:      make(chan []byte, HubChannelBufferSize),
		DroneMessages:  make(chan []byte, HubChannelBufferSize),
		UIMessages:     make(chan []byte, HubChannelBufferSize),
		DroneClients:   make(map[*Client]bool),
		UIClients:      make(map[*Client]bool),
	}
}

// Run is the main hub goroutine that handles all events via channels
// This is the central message router - all client communication flows through here
func (h *Hub) Run() {
	for {
		select {
		case client := <-h.Register:
			// Channel-based client registration
			h.registerClient(client)

		case client := <-h.Unregister:
			// Channel-based client unregistration
			h.unregisterClient(client)

		case message := <-h.Broadcast:
			// Broadcast message to all UI clients
			h.broadcastToUIClients(message)

		case message := <-h.DroneMessages:
			// Messages from drones - handle and broadcast to UI clients
			h.handleDroneMessage(message)

		case message := <-h.UIMessages:
			// Messages from UI - handle and route to appropriate drone
			h.handleUIMessage(message)
		}
	}
}

// registerClient adds a client and starts its listener goroutine
// Uses channel-based routing - no mutex locks
func (h *Hub) registerClient(client *Client) {
	// Initialize client health tracking
	client.lastPingTime = time.Now()
	client.missedPings = 0
	client.isHealthy = true

	// Initialize channels
	client.Send = make(chan []byte, ClientSendBufferSize)
	client.Receive = make(chan []byte, ClientReceiveBufferSize)
	client.quit = make(chan struct{})

	switch client.ClientType {
	case DroneClient:
		h.mu.Lock()
		h.DroneClients[client] = true
		h.mu.Unlock()
		log.Printf("📡 Drone client registered: %s (Total drones: %d)", client.DroneID, h.getDroneCount())

		// Start listener for drone's receive channel
		go h.droneMessageListener(client)

	case UIClient:
		h.mu.Lock()
		h.UIClients[client] = true
		h.mu.Unlock()
		log.Printf("🖥️  UI client registered (Total UI: %d)", h.getUICount())

		// Start listener for UI's receive channel
		go h.uiMessageListener(client)

	default:
		log.Printf("⚠️  Unknown client type: %s", client.ClientType)
	}
}

// unregisterClient removes a client and cleans up
// Uses channel-based unregistration - no mutex locks
func (h *Hub) unregisterClient(client *Client) {
	// Signal the client to stop its pumps
	close(client.quit)

	// Stop health check ticker if running
	if client.healthCheckTicker != nil {
		client.healthCheckTicker.Stop()
	}

	switch client.ClientType {
	case DroneClient:
		h.mu.Lock()
		if _, ok := h.DroneClients[client]; ok {
			delete(h.DroneClients, client)
			h.mu.Unlock()

			// Close channels
			close(client.Send)
			close(client.Receive)

			// Remove from global drone state
			DroneMutex.Lock()
			delete(Drones, client.DroneID)
			DroneMutex.Unlock()

			if client.isHealthy {
				log.Printf("🛑 Drone client unregistered: %s (Total drones: %d)", client.DroneID, h.getDroneCount())
			} else {
				log.Printf("💔 Drone client disconnected (unhealthy): %s (Total drones: %d)", client.DroneID, h.getDroneCount())
			}
		} else {
			h.mu.Unlock()
		}

	case UIClient:
		h.mu.Lock()
		if _, ok := h.UIClients[client]; ok {
			delete(h.UIClients, client)
			h.mu.Unlock()

			// Close channels
			close(client.Send)
			close(client.Receive)

			log.Printf("🖥️  UI client unregistered (Total UI: %d)", h.getUICount())
		} else {
			h.mu.Unlock()
		}
	}
}

// droneMessageListener listens to a drone client's receive channel
// and routes messages to the hub's DroneMessages channel
// This is the ReadPump → Hub routing: WS → Receive → Hub
func (h *Hub) droneMessageListener(client *Client) {
	defer func() {
		// Signal hub to unregister this client
		h.Unregister <- client
	}()

	for {
		select {
		case message, ok := <-client.Receive:
			if !ok {
				// Channel closed, client disconnected
				return
			}
			// Route to hub for processing
			select {
			case h.DroneMessages <- message:
			default:
				log.Printf("⚠️  DroneMessages channel full for %s", client.getClientIdentifier())
			}

		case <-client.quit:
			// Received quit signal
			return
		}
	}
}

// uiMessageListener listens to a UI client's receive channel
// and routes messages to the hub's UIMessages channel
// This is the ReadPump → Hub routing: WS → Receive → Hub
func (h *Hub) uiMessageListener(client *Client) {
	defer func() {
		// Signal hub to unregister this client
		h.Unregister <- client
	}()

	for {
		select {
		case message, ok := <-client.Receive:
			if !ok {
				// Channel closed, client disconnected
				return
			}
			// Route to hub for processing
			select {
			case h.UIMessages <- message:
			default:
				log.Printf("⚠️  UIMessages channel full for %s", client.getClientIdentifier())
			}

		case <-client.quit:
			// Received quit signal
			return
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
		// Parse position data and update DroneState map
		h.handleSendPosition(message)
		// Broadcast to UI clients
		h.broadcastToUIClients(message)

	case MessageTypeSurvivorDetected:
		// Parse survivor detection from drone
		h.handleSurvivorDetected(message)
		// Broadcast to UI clients
		h.broadcastToUIClients(message)

	default:
		// Forward other drone messages to UI
		h.broadcastToUIClients(message)
	}
}

// handleSendPosition updates the DroneState map with the drone's current position
func (h *Hub) handleSendPosition(message []byte) {
	var posMsg struct {
		Type      string  `json:"type"`
		DroneID   string  `json:"drone_id"`
		X         float64 `json:"x"`
		Y         float64 `json:"y"`
		Z         float64 `json:"z"`
		Timestamp int64   `json:"timestamp"`
	}

	if err := json.Unmarshal(message, &posMsg); err != nil {
		log.Printf("⚠️  Error parsing position message: %v", err)
		return
	}

	// Update drone state with thread-safe access
	DroneMutex.Lock()
	defer DroneMutex.Unlock()

	Drones[posMsg.DroneID] = &DroneState{
		ID:        posMsg.DroneID,
		X:         posMsg.X,
		Y:         posMsg.Y,
		Z:         posMsg.Z,
		Timestamp: time.UnixMilli(posMsg.Timestamp),
	}

	log.Printf("📍 Drone %s position updated: (%.2f, %.2f, %.2f)", posMsg.DroneID, posMsg.X, posMsg.Y, posMsg.Z)
}

// handleSurvivorDetected logs and processes survivor detection events
func (h *Hub) handleSurvivorDetected(message []byte) {
	var detectMsg struct {
		Type      string  `json:"type"`
		DroneID   string  `json:"drone_id"`
		X         float64 `json:"x"`
		Y         float64 `json:"y"`
		Z         float64 `json:"z"`
		Confidence float64 `json:"confidence"`
		Timestamp int64   `json:"timestamp"`
	}

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
		log.Printf("⚠️  Broadcast channel full, dropping message")
	}
}

// BroadcastToDrones sends a message to all connected drone clients
func (h *Hub) BroadcastToDrones(message []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for client := range h.DroneClients {
		select {
		case client.Send <- message:
		default:
			// If send channel is full, log and remove unhealthy client
			log.Printf("⚠️  Removing unresponsive drone client: %s (send channel full)", client.getClientIdentifier())
			// Signal unregister via channel
			go func(c *Client) {
				h.Unregister <- c
			}(client)
		}
	}
}

// broadcastToUIClients sends to all UI clients using channel-based routing
func (h *Hub) broadcastToUIClients(message []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	for client := range h.UIClients {
		select {
		case client.Send <- message: 
		default:
			// If send channel is full, log and handle gracefully
			log.Printf("⚠️  Removing unresponsive UI client (send channel full)")
			go func(c *Client) {
				h.Unregister <- c
			}(client)
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
// Scan Handler — GET /scan
// =============================================================================

// ThermalReading is a single raw thermal data point returned by /scan.
// The drone interprets temp_celsius: >30°C likely survivor, 14–26°C background.
type ThermalReading struct {
	X           float64 `json:"x"`
	Y           float64 `json:"y"`
	TempCelsius float64 `json:"temp_celsius"`
}

// ScanHandler handles GET /scan?x=&y=&z=&radius=
// Returns raw thermal readings for all objects within the scan radius.
// Survivors emit 36–37.5 °C; buildings emit 14–18 °C background heat.
// The drone calls this instead of generating random detections.
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
	if scanRadius <= 0 {
		scanRadius = 5
	}

	readings := []ThermalReading{}

	// Survivors — body heat 36–37.5 °C, falls off with distance
	SurvivorsMutex.RLock()
	for _, s := range Survivors {
		dx := s.X - droneX
		dy := s.Z - droneY // Survivor.Z is ground plane; drone Y is also ground plane
		dist := math.Sqrt(dx*dx + dy*dy)
		if dist <= scanRadius {
			apparent := s.Thermal * math.Exp(-dist*0.1)
			noise := (rand.Float64() - 0.5) * 0.4
			temp := math.Round((apparent+noise)*10) / 10
			readings = append(readings, ThermalReading{X: s.X, Y: s.Z, TempCelsius: temp})
		}
	}
	SurvivorsMutex.RUnlock()

	// Buildings — cooler background heat 14–18 °C, falls off faster
	BuildingsMutex.RLock()
	for _, b := range Buildings {
		dx := b.X - droneX
		dy := b.Y - droneY
		dist := math.Sqrt(dx*dx + dy*dy)
		if dist > 0 && dist <= scanRadius {
			apparent := b.Thermal * math.Exp(-dist*0.3)
			noise := (rand.Float64() - 0.5) * 0.3
			temp := math.Round((apparent+noise)*10) / 10
			readings = append(readings, ThermalReading{X: b.X, Y: b.Y, TempCelsius: temp})
		}
	}
	BuildingsMutex.RUnlock()

	_ = droneZ // altitude penalty reserved for Phase 4

	json.NewEncoder(w).Encode(readings)
}

// upgrader configures the WebSocket upgrader
var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	// TODO: Enable origin checking in production
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

// ReadPump reads messages from the WebSocket connection
// Routes to client's Receive channel → Hub listener → Hub routing
// Standardized pattern: WS → Receive channel → Hub
func (c *Client) ReadPump() {
	defer func() {
		if !c.isHealthy {
			log.Printf("🔴 ReadPump: Connection marked unhealthy, initiating cleanup for %s", c.getClientIdentifier())
		}
		c.Conn.Close()
	}()

	c.Conn.SetReadLimit(512 * 1024) // 512KB max message size
	c.Conn.SetReadDeadline(time.Now().Add(ServerReadDeadline))
	c.Conn.SetPongHandler(func(string) error {
		// Update health status on successful pong
		c.lastPingTime = time.Now()
		c.missedPings = 0
		c.isHealthy = true
		c.Conn.SetReadDeadline(time.Now().Add(ServerReadDeadline))
		return nil
	})

	for {
		_, message, err := c.Conn.ReadMessage()
		if err != nil {
			// Determine the type of error
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure, websocket.CloseNormalClosure) {
				log.Printf("❌ WebSocket error for %s: %v", c.getClientIdentifier(), err)
			} else if netErr, ok := err.(net.Error); ok && netErr.Timeout() {
				log.Printf("⏱️  Read timeout for %s - connection may be stale", c.getClientIdentifier())
			} else {
				log.Printf("📴 Connection closed for %s: %v", c.getClientIdentifier(), err)
			}
			// Mark as unhealthy before breaking
			c.isHealthy = false
			break
		}

		// Update health status on any message received
		c.lastPingTime = time.Now()
		c.missedPings = 0
		c.isHealthy = true

		// Write to client's receive channel - hub listener will pick it up
		// This is the key queue-based routing: WS → Receive → Hub
		select {
		case c.Receive <- message:
			// Message queued for hub to process
		default:
			log.Printf("⚠️  Receive channel full for %s, dropping message", c.getClientIdentifier())
		}
	}
}

// WritePump writes messages from the Send channel to the WebSocket connection
// Includes ping/pong handling and graceful shutdown
// Thread-safe: uses channel as message queue - WritePump is the only writer
// Standardized pattern: Hub → Send channel → WS
func (c *Client) WritePump() {
	// Create ticker for periodic pings
	ticker := time.NewTicker(ServerPingInterval)
	defer func() {
		ticker.Stop()
		// Ensure connection is closed properly
		if c.Conn != nil {
			c.Conn.Close()
		}
	}()

	for {
		select {
		case message, ok := <-c.Send:
			// Channel acts as message queue - WritePump serializes all writes
			c.Conn.SetWriteDeadline(time.Now().Add(ServerWriteDeadline))
			if !ok {
				// Hub closed the channel - send close message and return gracefully
				log.Printf("📤 WritePump: Send channel closed for %s", c.getClientIdentifier())
				c.Conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			// Write text message (no mutex needed - WritePump is sole writer)
			if err := c.Conn.WriteMessage(websocket.TextMessage, message); err != nil {
				log.Printf("❌ Write error for %s: %v", c.getClientIdentifier(), err)
				c.isHealthy = false
				return
			}

		case <-ticker.C:
			// Send ping to keep connection alive
			c.Conn.SetWriteDeadline(time.Now().Add(ServerWriteDeadline))
			if err := c.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				log.Printf("⚠️  Ping failed for %s: %v", c.getClientIdentifier(), err)
				c.isHealthy = false
				return
			}
			log.Printf("📶 Ping sent to %s", c.getClientIdentifier())

		case <-c.quit:
			// Received quit signal
			log.Printf("📤 WritePump: Received quit signal for %s", c.getClientIdentifier())
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
// Uses queue-based architecture: client sends to Receive channel, receives via Send channel
func ServeWs(hub *Hub, w http.ResponseWriter, r *http.Request, clientType string) {
	// Upgrade HTTP to WebSocket
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Println("WebSocket upgrade error:", err)
		return
	}

	// Extract drone ID if this is a drone client
	droneID := ""
	if clientType == DroneClient {
		droneID = r.URL.Query().Get("drone_id")
		if droneID == "" {
			droneID = generateDroneID()
		}
	}

	// Create new client with channels (queue-based architecture)
	// Note: Channels are initialized in registerClient to ensure proper setup
	client := &Client{
		Hub:        hub,
		Conn:       conn,
		ClientType: clientType,
		DroneID:    droneID,
		quit:       make(chan struct{}),
	}

	// Register client with hub via channel (queue-based)
	hub.Register <- client

	// Start read and write pumps in separate goroutines
	// WritePump: reads from Send channel → writes to WebSocket
	// ReadPump: reads from WebSocket → writes to Receive channel
	go client.WritePump()
	go client.ReadPump()

	// Send initial connection response with grid snapshot and Command Base coordinates
	// Note: The frontend maps: backend Y -> Three.js Z (ground), backend Z -> Three.js Y (altitude)
	// Command Base is at Three.js [0, 0.1, 40], so backend should send Y=40 (ground), Z=10 (altitude)
	// Merge building footprint cells with rubble blocked areas
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
				Y: 40.0,
			},
		},
		Position: Position{
			X: BaseX,
			Y: 40.0,
			Z: 10.0,
		},
		Survivors: []Survivor{}, // Survivors are secret — discovered only via /scan thermal readings
		Buildings: Buildings,
	}

	responseJSON, err := json.Marshal(initialResponse)
	if err == nil {
		select {
		case client.Send <- responseJSON:
			log.Printf("📤 Sent init_connection to %s: %d survivors, %d buildings",
				client.getClientIdentifier(), len(GetSurvivors()), len(Buildings))
		default:
			log.Printf("Failed to send initial connection to client")
		}
	}

	// Drone clients use "intention" field (MH's map_client convention).
	// Send a separate grid_snapshot so A* pathfinding gets building blocked cells.
	if clientType == DroneClient {
		droneGrid := map[string]interface{}{
			"intention": "grid_snapshot",
			"timestamp": time.Now().UnixMilli(),
			"blocked":   allBlocked,
		}
		if droneGridJSON, err2 := json.Marshal(droneGrid); err2 == nil {
			select {
			case client.Send <- droneGridJSON:
				log.Printf("📤 Sent grid_snapshot (intention) to drone %s: %d blocked cell(s)", droneID, len(allBlocked))
			default:
				log.Printf("Failed to send grid_snapshot to drone %s", droneID)
			}
		}
	}
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
