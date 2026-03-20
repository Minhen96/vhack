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

    "## CRITICAL RULES — follow exactly\n"
    "- NEVER call get_drone_capabilities, get_drone_status, or get_battery_status.\n"
    "- NEVER call move_to or thermal_scan directly — start_search handles all movement and scanning.\n"
    "- NEVER poll list_active_drones while searches are running — use wait_for_event instead.\n"
    "- Call start_search for ALL scanner drones IN THE SAME MESSAGE (parallel, each returns in <1s).\n"
    "- NEVER compute zones manually — always use plan_search_zones.\n\n"

    "## Mission Protocol\n\n"

    "PHASE 1 — Initialization:\n"
    "  1. Call get_map_info to discover map bounds (x_min, x_max, y_min, y_max) and base position.\n"
    "  2. Call list_active_drones to discover the fleet.\n\n"

    "PHASE 2 — Zone assignment and search:\n"
    "  1. Collect all scanner drone IDs from Phase 1.\n"
    "  2. Call plan_search_zones(drone_ids=[...scanner IDs...]).\n"
    "     Returns pre-calculated non-overlapping zones — one vertical X-strip per drone.\n"
    "     Each drone starts at base and fans out in a different X direction immediately.\n"
    "  3. Call start_search IN PARALLEL for every scanner drone using the returned zone coords.\n"
    "     Use z=15, step=10. Drones automatically skip cells already covered from a prior sweep.\n\n"

    "PHASE 3 — Event loop: call wait_for_event(timeout=30) repeatedly until all drones complete.\n"
    "  On survivor_found    → call delivery_aid(drone_id, x, y, z=0) using a delivery drone only.\n"
    "                          Log coordinates if no delivery drone is available. Then wait_for_event.\n"
    "  On battery_low       → do NOT call return_to_base. Drone returns automatically. Then wait_for_event.\n"
    "  On search_complete   → record the drone (note aborted=True/False).\n"
    "                          The drone is now returning to base — do NOT call start_search yet.\n"
    "                          Keep waiting for its charging_complete before re-dispatching.\n"
    "  On charging_complete → a drone finished charging and is ready. Record it.\n"
    "                          If ALL started drones have sent BOTH search_complete AND charging_complete:\n"
    "                            go to PHASE 4.\n"
    "                          Else if only some drones are done: keep waiting.\n"
    "  On drone_joined      → a new drone connected mid-mission.\n"
    "                          Call list_active_drones to get the updated fleet.\n"
    "                          Call plan_search_zones with ALL current scanner IDs (including the new one).\n"
    "                          Call start_search ONLY for the new drone using its assigned zone.\n"
    "                          Do NOT restart existing searches. Then wait_for_event.\n"
    "  On drone_left        → remove that drone from your active list.\n"
    "                          If that drone had an active search, treat it as search_complete AND charging_complete (aborted=True).\n"
    "                          If all started drones are now done, go to PHASE 4.\n"
    "                          Otherwise keep waiting.\n"
    "  On timeout           → call wait_for_event again (searches still running).\n\n"

    "PHASE 4 — Mission review (all drones are charged and idle at this point):\n"
    "  If ALL searches completed (aborted=False) and survivors_found=0 across all drones:\n"
    "    Go back to PHASE 2 using step=5, z=5 for a finer sweep.\n"
    "  Else if ANY search was aborted=True:\n"
    "    Go back to PHASE 2 immediately — drones are already charged.\n"
    "  Else: mission complete — summarize survivors found and aid delivered.\n\n"

    "## Map & Coordinates\n"
    "- Call get_map_info() first — it returns the live base position and search area bounds.\n"
    "- Base is at the north edge of the map. Drones spawn and charge there.\n"
    "- Buildings 3–10 units tall. z=15 clears all buildings (fast sweep). z=5 gives stronger thermal signal.\n\n"

    "## Thermal Interpretation\n"
    "- survivor_found events are already filtered to >30 °C (human body heat range).\n"
    "- Deliver aid to every survivor_found coordinate — do not skip any.\n\n"

    "## Battery\n"
    "- Drains 0.1 %/cell moved, 0.5 % per scan. start_search aborts automatically if battery is too low to return.\n"
    "- battery_low event fires when battery < 20 % — drone returns automatically, do NOT call return_to_base.\n"
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
    "array": list,
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

    # Flush any stale events (e.g. drone_joined from startup registrations)
    # that accumulated before this mission began.
    from backend.events import clear as clear_events
    from backend.coverage import coverage
    discarded = clear_events()
    if discarded:
        log.add("system", {"message": f"Flushed {discarded} stale event(s) from queue."})
    coverage.reset()
    log.add("system", {"message": "Coverage grid reset for new mission."})

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
