"""
FastAPI entry point
===================
Mounts the MCP server over HTTP (Streamable HTTP transport) so the
LangChain Command Agent can connect to it as a remote MCP server.

Run:
    uvicorn backend.main:app --reload --port 8000

MCP endpoint: http://localhost:8000/mcp/mcp
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers.drone import router as drone_router
from backend.api.routers.mission import router as mission_router
from backend.mcp.server import mcp

# Create the MCP sub-app first so the session_manager becomes available
mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the MCP session manager so it can accept connections."""
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Rescue Drone Command API",
    description="Autonomous drone fleet management for earthquake disaster response.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Drone registration endpoints
app.include_router(drone_router)

# Mission control API
app.include_router(mission_router)

# Mount the MCP server — accessible at /mcp/mcp
app.mount("/mcp", mcp_app)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
