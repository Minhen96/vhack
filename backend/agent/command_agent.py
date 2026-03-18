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
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pydantic import Field, create_model

load_dotenv()

logger = logging.getLogger(__name__)

GRID_SIZE = int(os.getenv("GRID_SIZE", "30"))

SYSTEM_PROMPT = (
    "You are an Autonomous Rescue Drone Command Agent operating in an "
    "earthquake disaster zone. Your mission is to coordinate a fleet of "
    "rescue drones to search for and aid survivors.\n\n"
    "## Operating Procedures\n"
    "1. ALWAYS start by calling `list_active_drones` to discover the current "
    "fleet. Never hard-code drone IDs.\n"
    "2. Check each drone's capabilities with `get_drone_capabilities`.\n"
    "3. Divide the search area into sectors and assign drones to maximise "
    "coverage. Explain your sector plan.\n"
    "4. Move drones using `move_to`, then run `thermal_scan` at each "
    "position.\n"
    "5. When survivors are detected, use `delivery_aid` to send supplies to "
    "the survivor coordinates.\n"
    "6. CRITICAL: Monitor battery after EVERY action. If a drone's battery "
    "drops below 20 %, immediately call `request_backup`, then "
    "`return_to_base` on the low-battery drone.\n"
    "7. Explain your reasoning step-by-step before each decision "
    "(chain-of-thought).\n\n"
    "## Environment\n"
    f"- Disaster zone: {GRID_SIZE}×{GRID_SIZE} grid\n"
    "- Base station: (0, 0, 0)\n"
    "- Standard flight altitude: z = 10\n"
    "- Battery drains 0.5 % per unit distance moved, 5 % per scan, "
    "5 % per delivery\n"
    "- Low battery threshold: 20 %\n"
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

                # Run the agent
                result = await agent.ainvoke({
                    "messages": [
                        SystemMessage(content=SYSTEM_PROMPT),
                        HumanMessage(content=objective),
                    ],
                })

                # ---- extract mission log from message history ---------------
                for msg in result["messages"]:
                    if isinstance(msg, AIMessage):
                        # Reasoning / chain-of-thought
                        if msg.content:
                            text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                            log.add("reasoning", {"message": text})
                        # Tool calls issued by the agent
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                log.add("tool_call", {
                                    "tool": tc["name"],
                                    "args": tc["args"],
                                })
                    elif isinstance(msg, ToolMessage):
                        content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
                        log.add("tool_result", {
                            "tool": msg.name,
                            "result": content[:800],
                        })

                # Final output — last AI message without tool calls
                final_msgs = [
                    m for m in result["messages"]
                    if isinstance(m, AIMessage)
                    and m.content
                    and not (hasattr(m, "tool_calls") and m.tool_calls)
                ]
                output = (
                    final_msgs[-1].content if final_msgs else "Mission completed."
                )

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
