from __future__ import annotations

from starlette.requests import HTTPConnection

from backend.simulation import Simulation
from backend.core.ws import ConnectionManager


def get_sim(conn: HTTPConnection) -> Simulation:
    """Inject the shared Simulation instance. Works for HTTP and WebSocket routes."""
    return conn.app.state.sim  # type: ignore[no-any-return]


def get_manager(conn: HTTPConnection) -> ConnectionManager:
    """Inject the shared ConnectionManager. Works for HTTP and WebSocket routes."""
    return conn.app.state.manager  # type: ignore[no-any-return]
