package main

import (
	"encoding/json"
	"flag"
	"log"
	"math/rand"
	"net/http"
	"os"
	"os/signal"
	"syscall"
)

// =============================================================================
// HTTP Handlers
// =============================================================================

// serveDrone handles WebSocket connections for drone clients
func serveDrone(hub *Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ServeWs(hub, w, r, DroneClient)
	}
}

// serveUI handles WebSocket connections for UI clients
func serveUI(hub *Hub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ServeWs(hub, w, r, UIClient)
	}
}

// healthHandler returns the health status of the server
func healthHandler(w http.ResponseWriter, r *http.Request) {
	// Only allow GET method for health check
	if r.Method != http.MethodGet {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	// Set content type to JSON
	w.Header().Set("Content-Type", "application/json")

	// Return health status
	response := map[string]string{"status": "ok"}
	if err := json.NewEncoder(w).Encode(response); err != nil {
		log.Printf("Error encoding health response: %v", err)
	}
}

// =============================================================================
// Main Function
// =============================================================================

func main() {
	// Define command-line flags
	serverMode := flag.Bool("server", false, "Run as WebSocket server")
	droneMode := flag.Bool("drone", false, "Run as mock drone client")
	flag.Parse()

	// If no mode specified, default to server
	if !*serverMode && !*droneMode {
		*serverMode = true
	}

	if *droneMode {
		// Run as drone client
		RunDroneClient()
		return
	}

	// Run as server
	runServer()
}

func runServer() {
	// Get port from environment variable, default to 8080
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	// Generate random survivors for the simulation (5-10 survivors)
	survivorCount := 5 + rand.Intn(6) // 5 to 10
	log.Printf("🎯 Generating %d survivors for the disaster simulation...", survivorCount)
	Survivors = GenerateSurvivors(survivorCount)

	// Generate buildings (5-8 uncorrupted buildings as obstacles)
	buildingCount := 5 + rand.Intn(4) // 5 to 8
	log.Printf("🏢 Generating %d buildings...", buildingCount)
	Buildings = GenerateBuildings(buildingCount)
	buildOccupancyGrid()

	// Create a new Hub instance
	hub := NewHub()

	// Start the hub's Run method in a goroutine
	go hub.Run()

	// Log startup
	log.Printf("Starting WebSocket Hub on port %s", port)

	// Set up HTTP routes
	mux := http.NewServeMux()

	// WebSocket endpoint for drone connections
	mux.HandleFunc("/ws/drone", serveDrone(hub))

	// WebSocket endpoint for UI connections
	mux.HandleFunc("/ws/ui", serveUI(hub))

	// Health check endpoint
	mux.HandleFunc("/health", healthHandler)

	// Thermal scan endpoint — drone calls this instead of random generation
	mux.HandleFunc("/scan", ScanHandler)

	// Configure server with timeouts
	server := &http.Server{
		Addr:           ":" + port,
		Handler:        mux,
		ReadTimeout:    60,
		WriteTimeout:   60,
		MaxHeaderBytes: 4096,
	}

	// Start server in a goroutine
	go func() {
		log.Printf("Server listening on http://localhost:%s", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	// Wait for interrupt signal for graceful shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	log.Println("Shutting down server...")

	// Give outstanding requests a chance to complete
	if err := server.Shutdown(nil); err != nil {
		log.Printf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited properly")
}
