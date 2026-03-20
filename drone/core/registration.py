from __future__ import annotations

import logging

import httpx

from drone.core.config import DRONE_HOST, DRONE_ID, DRONE_PORT, DRONE_TYPE, MCP_URL
from drone.models.drone import CAPABILITIES, COMMON_CAPABILITIES, DroneType

logger = logging.getLogger(__name__)


async def register_to_mcp() -> None:
    import asyncio

    payload = {
        "drone_id": DRONE_ID,
        "type": DRONE_TYPE,
        "capabilities": CAPABILITIES[DroneType(DRONE_TYPE)] + COMMON_CAPABILITIES,
        "host": DRONE_HOST,
        "port": DRONE_PORT,
    }
    for attempt in range(1, 6):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{MCP_URL}/register", json=payload, timeout=5.0)
                body = resp.json()

            if body.get("success") is True:
                logger.info("Registered to MCP: drone_id=%s", DRONE_ID)
            else:
                logger.warning("MCP registration unexpected response: %s", body)
            return

        except (httpx.ConnectError, httpx.ReadTimeout):
            if attempt < 5:
                logger.warning("MCP not ready (attempt %d/5) — retrying in 2s...", attempt)
                await asyncio.sleep(2)
            else:
                logger.warning("MCP server not reachable at %s after 5 attempts — running without registration.", MCP_URL)
        except Exception:
            logger.exception("Unexpected error during MCP registration.")
            return


async def deregister_from_mcp() -> None:
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{MCP_URL}/deregister",
                json={"drone_id": DRONE_ID},
                timeout=3.0,
            )
        logger.info("Deregistered from MCP: drone_id=%s", DRONE_ID)

    except httpx.ConnectError:
        logger.warning("MCP server not reachable during deregistration — skipping.")
    except Exception:
        logger.exception("Unexpected error during MCP deregistration.")