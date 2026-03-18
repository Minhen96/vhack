package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math/rand"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

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
	ServerReadDeadline = 60 * time.Second   // Read deadline (longer for reconnection resilience)
	ServerWriteDeadline = 10 * time.Second  // Write deadline for messages

	// Connection health monitoring
	HealthCheckInterval = 10 * time.Second    // How often to check connection health
	MaxMissedPings      = 3                   // Max missed pings before considering connection dead
	ConnectionTimeout   = 30 * time.Second     // Max time to establish initial connection
)

// =============================================================================
// Client Struct
// =============================================================================

// Client represents a WebSocket connection in the hub
type Client struct {
	// Hub is the pointer to the Hub that manages this client
	Hub *Hub
	// Conn is the WebSocket connection
	Conn *websocket.Conn
	// Send is a buffered channel for outgoing messages
	Send chan []byte
	// ClientType is either "drone" or "ui"
	ClientType string
	// DroneID is the unique identifier for drone clients (empty for UI)
	DroneID string

	// Connection health tracking
	lastPingTime    time.Time     // Last time we received a ping/activity
	missedPings     int           // Number of missed pings
	isHealthy      bool          // Connection health status
	healthCheckTicker *time.Ticker // Health check ticker
	wg             sync.WaitGroup // WaitGroup for graceful shutdown
}

// =============================================================================
// Hub Struct
// =============================================================================

// Hub maintains the set of active clients and broadcasts messages
type Hub struct {
	// DroneClients is the set of drone clients
	DroneClients map[*Client]bool
	// UIClients is the set of UI clients
	UIClients map[*Client]bool
	// Register is a channel for registering new clients
	Register chan *Client
	// Unregister is a channel for unregistering clients
	Unregister chan *Client
	// Broadcast is a channel for broadcast messages to UI clients
	Broadcast chan []byte
	// DroneMessages is a channel for messages from drones to route to UI
	DroneMessages chan *ClientMessage

	// unregisterChan is used to signal WritePump to stop
	unregisterChan chan struct{}

	// mutex for thread-safe access to client maps
	mu sync.RWMutex

	// Connection statistics
	totalConnections    int64
	totalDisconnections int64
}

// =============================================================================
// ClientMessage Struct
// =============================================================================

// ClientMessage represents a message from a client along with the client reference
type ClientMessage struct {
	Client  *Client
	Message []byte
}

// =============================================================================
// Hub Methods
// =============================================================================

// NewHub creates and returns a new Hub instance
func NewHub() *Hub {
	return &Hub{
		DroneClients:  make(map[*Client]bool),
		UIClients:     make(map[*Client]bool),
		Register:      make(chan *Client),
		Unregister:    make(chan *Client),
		Broadcast:     make(chan []byte),
		DroneMessages: make(chan *ClientMessage, 256),
	}
}

// Run is the main hub goroutine that handles all events
func (h *Hub) Run() {
	for {
		select {
		case client := <-h.Register:
			h.RegisterClient(client)

		case client := <-h.Unregister:
			h.UnregisterClient(client)

		case message := <-h.Broadcast:
			// Broadcast message to all UI clients (for telemetry data)
			h.broadcastToUIClients(message)

		case clientMessage := <-h.DroneMessages:
			// Messages from drones - broadcast to UI clients
			// For low latency: pass raw bytes without re-marshalling
			h.broadcastToUIClients(clientMessage.Message)
		}
	}
}

// RegisterClient adds a client to the appropriate pool based on ClientType
func (h *Hub) RegisterClient(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// Initialize client health tracking
	client.lastPingTime = time.Now()
	client.missedPings = 0
	client.isHealthy = true

	switch client.ClientType {
	case DroneClient:
		h.DroneClients[client] = true
		log.Printf("📡 Drone client registered: %s (Total drones: %d)", client.DroneID, len(h.DroneClients))
	case UIClient:
		h.UIClients[client] = true
		log.Printf("🖥️  UI client registered (Total UI: %d)", len(h.UIClients))
	default:
		log.Printf("⚠️  Unknown client type: %s", client.ClientType)
	}
}

// UnregisterClient removes a client from the pool and closes its Send channel
func (h *Hub) UnregisterClient(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// Stop health check ticker if running
	if client.healthCheckTicker != nil {
		client.healthCheckTicker.Stop()
	}

	switch client.ClientType {
	case DroneClient:
		if _, ok := h.DroneClients[client]; ok {
			delete(h.DroneClients, client)
			close(client.Send)
			if client.isHealthy {
				log.Printf("🛑 Drone client unregistered: %s (Total drones: %d)", client.DroneID, len(h.DroneClients))
			} else {
				log.Printf("💔 Drone client disconnected (unhealthy): %s (Total drones: %d)", client.DroneID, len(h.DroneClients))
			}
		}
	case UIClient:
		if _, ok := h.UIClients[client]; ok {
			delete(h.UIClients, client)
			close(client.Send)
			log.Printf("🖥️  UI client unregistered (Total UI: %d)", len(h.UIClients))
		}
	}
}

// BroadcastToUI sends a message to all connected UI clients
// This is called when a drone sends send_position or survivor_detected
func (h *Hub) BroadcastToUI(message []byte) {
	h.Broadcast <- message
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
			// Note: We can't delete from map while holding read lock
			// The client will be removed when it fails to send
			go func(c *Client) {
				h.Unregister <- c
			}(client)
		}
	}
}

// broadcastToUIClients is an internal method that sends to UI clients
// Uses read lock for better performance
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

// GetInitialGridSnapshot returns the initial grid snapshot with hardcoded obstacles
func (h *Hub) GetInitialGridSnapshot() GridSnapshot {
	return GridSnapshot{
		Type:      MessageTypeGridSnapshot,
		Timestamp: time.Now().UnixMilli(),
		Blocked: []BlockedArea{
			{X: 10, Y: 10, Radius: 5},
			{X: 25, Y: 30, Radius: 8},
			{X: 50, Y: 20, Radius: 6},
		},
	}
}

// =============================================================================
// Client Methods
// =============================================================================

// upgrader configures the WebSocket upgrader
var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	// TODO: Enable origin checking in production
	// CheckOrigin: func(r *http.Request) bool {
	//     allowedOrigins := os.Getenv("ALLOWED_ORIGINS")
	//     if allowedOrigins == "" {
	//         return true
	//     }
	//     origin := r.Header.Get("Origin")
	//     for _, allowed := range strings.Split(allowedOrigins, ",") {
	//         if strings.TrimSpace(allowed) == origin {
	//             return true
	//         }
	//     }
	//     return false
	// },
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

// ReadPump reads messages from the WebSocket connection
// For drones: sends the raw message to Hub.DroneMessages for broadcasting to UI
// For UI: keeps connection alive (UI doesn't send messages upstream in this spec)
func (c *Client) ReadPump() {
	defer func() {
		// Log the reason for disconnecting
		if !c.isHealthy {
			log.Printf("🔴 ReadPump: Connection marked unhealthy, initiating cleanup for %s", c.getClientIdentifier())
		}
		c.Hub.Unregister <- c
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

		// Parse the message to get the "type" field for routing
		var msgType struct {
			Type string `json:"type"`
		}

		if err := json.Unmarshal(message, &msgType); err != nil {
			log.Printf("⚠️  Error parsing message from %s: %v", c.getClientIdentifier(), err)
			continue
		}

		// Route message based on client type
		if c.ClientType == DroneClient {
			// For drones, forward the raw message to be broadcast to UI
			// Low latency: pass raw bytes without re-marshalling
			select {
			case c.Hub.DroneMessages <- &ClientMessage{
				Client:  c,
				Message: message,
			}:
			default:
				// If channel is full, log but don't drop the client
				log.Printf("⚠️  Drone message channel full for %s", c.getClientIdentifier())
			}
		} else if c.ClientType == UIClient {
			// For UI clients, we don't expect upstream messages in this spec
			// Just log for debugging
			log.Printf("📥 Received message from UI client: %s", msgType.Type)
		}
	}
}

// WritePump writes messages from the Send channel to the WebSocket connection
// Includes ping/pong handling and graceful shutdown
func (c *Client) WritePump() {
	// Create ticker for periodic pings - use the configured interval
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
			c.Conn.SetWriteDeadline(time.Now().Add(ServerWriteDeadline))
			if !ok {
				// Hub closed the channel - send close message and return gracefully
				log.Printf("📤 WritePump: Send channel closed for %s", c.getClientIdentifier())
				c.Conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}

			// Write text message
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
			// Log ping sent (debug level)
			log.Printf("📶 Ping sent to %s", c.getClientIdentifier())

		case <-c.Hub.unregisterChan:
			// Received signal to unregister
			log.Printf("📤 WritePump: Received unregister signal for %s", c.getClientIdentifier())
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

	// Create new client
	client := &Client{
		Hub:        hub,
		Conn:       conn,
		Send:       make(chan []byte, 256), // Buffered channel
		ClientType: clientType,
		DroneID:    droneID,
	}

	// Register client with hub
	hub.Register <- client

	// Start read and write pumps in separate goroutines
	go client.WritePump()
	go client.ReadPump()

	// Send initial grid snapshot to the new client
	initialGrid := hub.GetInitialGridSnapshot()
	gridJSON, err := json.Marshal(initialGrid)
	if err == nil {
		select {
		case client.Send <- gridJSON:
		default:
			log.Printf("Failed to send initial grid to client")
		}
	}
}

// generateDroneID generates a unique drone ID
func generateDroneID() string {
	return fmt.Sprintf("drone-%s-%04d", time.Now().Format("20060102150405"), rand.Intn(10000))
}
