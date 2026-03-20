#!/bin/bash

# dev.sh - Linux/macOS setup and run script for vHack

SETUP=false
RUN=false

# parse arguments
for arg in "$@"
do
    if [ "$arg" == "--setup" ] || [ "$arg" == "-s" ] || [ "$arg" == "setup" ]; then
        SETUP=true
    elif [ "$arg" == "--run" ] || [ "$arg" == "-r" ] || [ "$arg" == "run" ]; then
        RUN=true
    fi
done

# default to run if no flags provided
if [ "$SETUP" = false ] && [ "$RUN" = false ]; then
    RUN=true
fi

if [ "$SETUP" = true ]; then
    echo -e "\n--- Setting up environment ---"
    
    # 1. Python venv
    if [ ! -d ".venv" ]; then
        echo "[1/4] Creating Python virtual environment..."
        python3 -m venv .venv
    else
        echo "[1/4] Python virtual environment already exists."
    fi
    echo "Installing/Updating Python dependencies..."
    ./.venv/bin/pip install --upgrade pip
    ./.venv/bin/pip install -r requirements.txt

    # 2. Go dependencies
    echo -e "\n[2/4] Checking Go environment..."
    if command -v go &> /dev/null; then
        cd drone-sim-server
        echo "Downloading Go dependencies..."
        go mod download
        cd ..
    else
        echo "Warning: Go not found in PATH. Skipping Go setup."
    fi

    # 3. Frontend dependencies
    echo -e "\n[3/4] Checking Frontend dependencies..."
    cd frontend
    if command -v pnpm &> /dev/null; then
        echo "Installing with pnpm..."
        pnpm install
    elif command -v npm &> /dev/null; then
        echo "Installing with npm..."
        npm install
    else
        echo "Warning: npm/pnpm not found in PATH. Skipping frontend setup."
    fi
    cd ..

    # 4. Environment variables
    echo -e "\n[4/4] Checking .env files..."
    env_files=(
        "backend/.env.example:backend/.env"
        "drone/.env.example:drone/.env"
        "drone-sim-server/.env.example:drone-sim-server/.env"
        "frontend/.env.example:frontend/.env"
        ".env.example:.env"
    )

    for item in "${env_files[@]}"; do
        EXAMPLE="${item%%:*}"
        TARGET="${item##*:}"
        if [ ! -f "$TARGET" ]; then
            if [ -f "$EXAMPLE" ]; then
                echo "Copying $EXAMPLE -> $TARGET"
                cp "$EXAMPLE" "$TARGET"
            fi
        else
            echo "Skipping $TARGET (already exists)"
        fi
    done

    echo -e "\nSetup complete!"
fi

if [ "$RUN" = true ]; then
    echo -e "\n--- Starting services ---"

    if [ ! -d ".venv" ]; then
        echo "Error: .venv not found. Please run ./dev.sh --setup first."
        exit 1
    fi

    # Cleanup handler to kill background processes on Ctrl+C
    trap "echo -e '\nStopping all services...'; kill 0" EXIT

    echo "Starting services in background..."

    # Start Go Sim Server (using a subshell to avoid directory change issues)
    if command -v go &> /dev/null; then
        (cd drone-sim-server && PORT=8080 go run . --server) &
    else
        echo "Warning: Go not found — skipping sim server. Install Go to enable it."
    fi

    # Start Backend
    ./.venv/bin/uvicorn backend.main:app --port 8000 --reload &

    # Wait for backend to be ready before starting drones
    echo "Waiting for backend to be ready..."
    for i in $(seq 1 30); do
        if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
            echo "Backend is ready."
            break
        fi
        sleep 1
    done

    # Start Drone #1 Scanner
    ./.venv/bin/uvicorn drone.main:app --port 8001 --reload &

    # Start Drone #2 Delivery
    DRONE_TYPE=delivery DRONE_PORT=8002 ./.venv/bin/uvicorn drone.main:app --port 8002 --reload &

    # Start Frontend
    if command -v pnpm &> /dev/null; then
        (cd frontend && pnpm run dev) &
    elif command -v npm &> /dev/null; then
        (cd frontend && npm run dev) &
    else
        echo "Warning: npm/pnpm not found — skipping frontend. Install Node.js to enable it."
    fi

    echo -e "\nAll services started. Press Ctrl+C to stop all."
    echo "- Sim Server: http://localhost:8080"
    echo "- Backend:    http://localhost:8000/docs"
    echo "- Drone 1:    http://localhost:8001/docs"
    echo "- Drone 2:    http://localhost:8002/docs"
    echo "- Frontend:   http://localhost:3000"
    
    # Wait for all background processes
    wait
fi
