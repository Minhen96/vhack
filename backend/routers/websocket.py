from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from backend.deps import get_manager, get_sim
from backend.simulation import Simulation
from backend.ws import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/updates")
async def websocket_updates(
    ws: WebSocket,
    sim: Annotated[Simulation, Depends(get_sim)],
    manager: Annotated[ConnectionManager, Depends(get_manager)],
) -> None:
    await manager.connect(ws)
    try:
        # Send full state snapshot so client can render immediately on connect
        await manager.send_to(
            ws,
            {
                "event": "init",
                "data": {
                    "mission": sim.mission.to_dict(),
                    "drones": sim.query_drones(),
                    "survivors": sim.query_survivors(),
                    "grid": sim.query_map_state(),
                    "heatmap": sim.query_heatmap(),
                },
            },
        )
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        logger.exception("Unexpected WebSocket error")
        manager.disconnect(ws)
