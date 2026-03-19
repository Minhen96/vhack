"""
Autonomous Command Agent
========================
Connects to the MCP server via Streamable HTTP transport, discovers drone
tools dynamically, and orchestrates search-and-rescue missions using
LangChain with chain-of-thought reasoning.

All communication with drones flows through the Model Context Protocol.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import Field, create_model

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

GRID_SIZE = int(os.getenv("GRID_SIZE", "30"))

SYSTEM_PROMPT = (
    "You are an Autonomous Rescue Drone Command Agent in an earthquake disaster zone.\n\n"

    "## CRITICAL EFFICIENCY RULES — follow these exactly\n"
    "- NEVER call get_drone_capabilities — you already know: scanner drones use search_area, delivery drones use delivery_aid.\n"
    "- NEVER call get_drone_status or get_battery_status before starting work. Only check battery IF a tool result warns it is low.\n"
    "- NEVER use move_to + thermal_scan in a loop — ALWAYS use search_area. It sweeps autonomously with zero LLM round-trips between steps.\n"
    "- Call search_area for ALL scanner drones IN THE SAME MESSAGE (parallel execution).\n\n"

    "## Mission Protocol (exactly 4 phases)\n"
    "PHASE 1 — call get_map_info and list_active_drones IN PARALLEL (same message, two tool calls).\n"
    "PHASE 2 — Search: use x_min/x_max/y_min/y_max from get_map_info to divide the map into sectors.\n"
    "  Call search_area for ALL scanner drones IN PARALLEL (same message).\n"
    "  Sector split by drone count:\n"
    "    1 scanner → search_area(x1=x_min, y1=y_min, x2=x_max, y2=y_max, z=15, step=10)\n"
    "    2 scanners → drone1: left half (x1=x_min, x2=0)  |  drone2: right half (x1=0, x2=x_max)\n"
    "    3 scanners → split into thirds along X axis\n"
    "PHASE 3 — Aid: for every item in detections[] returned by search_area, call delivery_aid immediately.\n"
    "  If survivors_detected=False, call search_area again on sub-areas with step=5, z=5.\n\n"

    "## Map & Coordinates\n"
    "- Base station: (0, 0). Drones start and charge here.\n"
    "- Buildings 3–10 units tall. z=15 clears all buildings (fast sweep). z=5 gives stronger thermal signal (confirmation).\n\n"

    "## Thermal Interpretation\n"
    "- >30 °C = likely survivor. 14–26 °C = building/rubble background. <10 °C = open ground.\n"
    "- search_area already filters: survivors_detected=True means ≥1 reading above 30 °C.\n"
    "- detections[] contains confirmed signals — deliver aid to each coordinate immediately.\n\n"

    "## Battery\n"
    "- Drains 0.5 %/cell moved, 1 % per scan, 1 % per delivery.\n"
    "- search_area aborts automatically if battery goes critical — check aborted field.\n"
    "- If battery < 20 % after search_area returns: call request_backup, then return_to_base.\n"
)


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _create_llm():
    """Instantiate the LLM based on the LLM_PROVIDER env-var."""
    provider = os.getenv("LLM_PROVIDER", "deepseek").lower()

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError(
                "Set GOOGLE_API_KEY in your .env file "
                "(copy .env.example → .env and fill in the key)."
            )
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            google_api_key=api_key,
            temperature=0,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            temperature=0,
        )

    if provider == "deepseek":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
            temperature=0,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. "
        "Use one of: gemini, openai, anthropic, deepseek."
    )


# ---------------------------------------------------------------------------
# MCP → LangChain tool adapter
# ---------------------------------------------------------------------------

_JSON_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
}


def _mcp_tool_to_langchain(
    session: ClientSession,
    mcp_tool,
) -> StructuredTool:
    """Wrap a single MCP tool as a LangChain StructuredTool."""
    schema = mcp_tool.inputSchema or {}
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))

    # Build a dynamic Pydantic model for the tool's arguments
    field_defs: dict[str, Any] = {}
    for name, prop in properties.items():
        py_type = _JSON_TYPE_MAP.get(prop.get("type", "string"), str)
        desc = prop.get("description", "")
        if name in required_fields:
            field_defs[name] = (py_type, Field(description=desc))
        else:
            field_defs[name] = (py_type, Field(default=None, description=desc))

    ArgsModel = create_model(
        f"{mcp_tool.name}_Args",
        **field_defs,
    ) if field_defs else create_model(f"{mcp_tool.name}_Args")

    # Capture tool name in closure
    tool_name = mcp_tool.name

    async def _call(**kwargs: Any) -> str:
        filtered = {k: v for k, v in kwargs.items() if v is not None}
        result = await session.call_tool(tool_name, filtered)
        parts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(parts) if parts else str(result.content)

    return StructuredTool(
        name=tool_name,
        description=mcp_tool.description or tool_name,
        coroutine=_call,
        args_schema=ArgsModel,
    )


# ---------------------------------------------------------------------------
# Mission log
# ---------------------------------------------------------------------------

class MissionLog:
    """Collects timestamped entries produced during a mission."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def add(self, event_type: str, data: dict[str, Any]) -> None:
        self.entries.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **data,
        })

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.entries)


# ---------------------------------------------------------------------------
# Global mission state
# ---------------------------------------------------------------------------

_current_log: MissionLog | None = None
_is_running = False


def get_mission_log() -> dict[str, Any] | None:
    """Return the current (or most recent) mission log."""
    if _current_log is None:
        return None
    return {
        "entries": _current_log.to_list(),
        "is_running": _is_running,
    }


# ---------------------------------------------------------------------------
# Mission runner
# ---------------------------------------------------------------------------

async def run_mission(objective: str) -> dict[str, Any]:
    """
    Execute a full search-and-rescue mission.

    1. Connect to the MCP server via Streamable HTTP.
    2. Discover available drone tools.
    3. Build a LangChain ReAct agent with those tools.
    4. Let the agent plan and execute the mission with CoT reasoning.
    5. Return a structured result with the full mission log.
    """
    global _current_log, _is_running  # noqa: PLW0603

    if _is_running:
        return {"status": "error", "error": "A mission is already in progress."}

    _is_running = True
    log = MissionLog()
    _current_log = log

    log.add("mission_start", {"objective": objective})

    mcp_url = os.getenv("MCP_URL", "http://localhost:8000/mcp/mcp")

    try:
        llm = _create_llm()
        log.add("system", {"message": f"LLM provider ready. Connecting to MCP at {mcp_url}"})

        # --- MCP connection --------------------------------------------------
        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()

                # Discover tools
                tools_result = await session.list_tools()
                tool_names = [t.name for t in tools_result.tools]
                log.add("tools_discovered", {
                    "count": len(tool_names),
                    "tools": tool_names,
                })

                # Convert MCP tools → LangChain tools
                lc_tools = [
                    _mcp_tool_to_langchain(session, t)
                    for t in tools_result.tools
                ]

                # Build the LangGraph ReAct agent
                agent = create_react_agent(llm, lc_tools)

                # Run the agent with streaming for real-time log updates
                final_msgs = []
                async for event in agent.astream_events(
                    {
                        "messages": [
                            SystemMessage(content=SYSTEM_PROMPT),
                            HumanMessage(content=objective),
                        ],
                    },
                    version="v2",
                    config={"recursion_limit": 100},
                ):
                    kind = event["event"]
                    name = event.get("name", "")
                    data = event.get("data", {})

                    if kind == "on_tool_start":
                        log.add("tool_call", {
                            "tool": name,
                            "args": data.get("input", {}),
                        })
                    elif kind == "on_tool_end":
                        raw = data.get("output", "")
                        content = str(raw)[:500] if raw is not None else ""
                        log.add("tool_result", {"tool": name, "result": content})
                    elif kind == "on_chat_model_end":
                        msg = data.get("output")
                        if msg and hasattr(msg, "content") and msg.content:
                            text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                            if not (hasattr(msg, "tool_calls") and msg.tool_calls):
                                final_msgs.append(text)
                            log.add("reasoning", {"message": text[:500]})

                output = final_msgs[-1] if final_msgs else "Mission completed."

                log.add("mission_complete", {"summary": output})
                _is_running = False
                return {
                    "status": "completed",
                    "output": output,
                    "log": log.to_list(),
                }

    except Exception as e:
        logger.exception("Mission failed")
        log.add("error", {"message": str(e)})
        _is_running = False
        return {
            "status": "error",
            "error": str(e),
            "log": log.to_list(),
        }
