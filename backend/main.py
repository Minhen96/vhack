"""
FastAPI entry point
===================
Mounts the MCP server over HTTP (Streamable HTTP transport) so the
LangChain Command Agent can connect to it as a remote MCP server.

Run:
    uvicorn backend.main:app --reload --port 8000

MCP endpoint: http://localhost:8000/mcp
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.mcp.server import mcp

app = FastAPI(
    title="Rescue Drone Command API",
    description="Autonomous drone fleet management for earthquake disaster response.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the MCP server — accessible at /mcp
app.mount("/mcp", mcp.streamable_http_app())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
