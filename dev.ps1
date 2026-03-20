# dev.ps1

param(
    [switch]$Setup,
    [switch]$Run
)

# Default to run if no flags provided
if (-not $Setup -and -not $Run) {
    $Run = $true
}

$root = Get-Location

if ($Setup) {
    Write-Host "`n--- Setting up environment ---" -ForegroundColor Cyan

    # 1. Python venv
    if (-not (Test-Path ".venv")) {
        Write-Host "[1/4] Creating Python virtual environment..."
        python -m venv .venv
    } else {
        Write-Host "[1/4] Python virtual environment already exists."
    }
    
    Write-Host "Installing/Updating Python dependencies..."
    & .venv\Scripts\python.exe -m pip install --upgrade pip
    & .venv\Scripts\python.exe -m pip install -r requirements.txt

    # 2. Go dependencies
    Write-Host "`n[2/4] Checking Go environment..."
    if (Get-Command go -ErrorAction SilentlyContinue) {
        Push-Location drone-sim-server
        Write-Host "Downloading Go dependencies..."
        go mod download
        Pop-Location
    } else {
        Write-Host "Warning: Go not found in PATH. Skipping Go setup." -ForegroundColor Yellow
    }

    # 3. Frontend dependencies
    Write-Host "`n[3/4] Checking Frontend dependencies..."
    Push-Location frontend
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        Write-Host "Installing with pnpm..."
        pnpm install
    } elseif (Get-Command npm -ErrorAction SilentlyContinue) {
        Write-Host "Installing with npm..."
        npm install
    } else {
        Write-Host "Warning: npm/pnpm not found in PATH. Skipping frontend setup." -ForegroundColor Yellow
    }
    Pop-Location

    # 4. Environment variables
    Write-Host "`n[4/4] Checking .env files..."
    $envFiles = @(
        @{ Example = "backend/.env.example"; Target = "backend/.env" },
        @{ Example = "drone/.env.example"; Target = "drone/.env" },
        @{ Example = "drone-sim-server/.env.example"; Target = "drone-sim-server/.env" },
        @{ Example = "frontend/.env.example"; Target = "frontend/.env" },
        @{ Example = ".env.example"; Target = ".env" }
    )

    foreach ($file in $envFiles) {
        $targetPath = Join-Path $root $file.Target
        $examplePath = Join-Path $root $file.Example
        
        if (-not (Test-Path $targetPath)) {
            if (Test-Path $examplePath) {
                Write-Host "Copying $($file.Example) -> $($file.Target)"
                Copy-Item $examplePath $targetPath
            }
        } else {
            Write-Host "Skipping $($file.Target) (already exists)"
        }
    }

    Write-Host "`nSetup complete!" -ForegroundColor Green
}

if ($Run) {
    Write-Host "`n--- Starting services ---" -ForegroundColor Cyan

    # Check if venv exists
    if (-not (Test-Path ".venv")) {
        Write-Host "Error: .venv not found. Please run .\dev.ps1 -Setup first." -ForegroundColor Red
        exit 1
    }

    $pythonPath = "$root\.venv\Scripts\python.exe"
    $uvicornPath = "$root\.venv\Scripts\uvicorn.exe"

    # Start Go Sim Server
    Write-Host "Starting Go Sim Server (8080)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Sim Server (8080)'; cd drone-sim-server; `$env:PORT='8080'; go run . --server"

    # Start Backend
    Write-Host "Starting Backend (8000)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Backend (8000)'; & '$uvicornPath' backend.main:app --port 8000 --reload"

    # Start Drone #1 (Detection)
    Write-Host "Starting Drone #1 Detection (8001)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Drone #1 (8001)'; `$env:DRONE_TYPE='scanner'; `$env:DRONE_PORT='8001'; & '$uvicornPath' drone.main:app --port 8001 --reload"

    # Start Drone #2 (Detection)
    Write-Host "Starting Drone #2 Detection (8002)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Drone #2 (8002)'; `$env:DRONE_TYPE='scanner'; `$env:DRONE_PORT='8002'; & '$uvicornPath' drone.main:app --port 8002 --reload"

    # Start Drone #3 (Aid)
    Write-Host "Starting Drone #3 Aid (8003)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Drone #3 (8003)'; `$env:DRONE_TYPE='delivery'; `$env:DRONE_PORT='8003'; & '$uvicornPath' drone.main:app --port 8003 --reload"

    # Start Drone #4 (Aid)
    Write-Host "Starting Drone #4 Aid (8004)..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Drone #4 (8004)'; `$env:DRONE_TYPE='delivery'; `$env:DRONE_PORT='8004'; & '$uvicornPath' drone.main:app --port 8004 --reload"

    # Start Frontend
    Write-Host "Starting Frontend (3000)..."
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Frontend (3000)'; cd frontend; pnpm run dev --port 3000"
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$Host.UI.RawUI.WindowTitle = 'Frontend (3000)'; cd frontend; npm run dev -- --port 3000"
    }

    Write-Host "`nAll services started in separate windows." -ForegroundColor Green
    Write-Host "- Sim Server: http://localhost:8080"
    Write-Host "- Backend:    http://localhost:8000/docs"
    Write-Host "- Drone 1:    http://localhost:8001/docs"
    Write-Host "- Drone 2:    http://localhost:8002/docs"
    Write-Host "- Drone 3:    http://localhost:8003/docs"
    Write-Host "- Drone 4:    http://localhost:8004/docs"
    Write-Host "- Frontend:   http://localhost:3000"
}
