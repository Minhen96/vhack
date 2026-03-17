"""
ARIA — Autonomous Rescue Intelligence Agent
-------------------------------------------
Runs an LLM-powered observe → plan → act loop, communicating with the
simulation exclusively through MCP tool wrappers.

The agent loop runs as an independent asyncio task so a slow LLM response
never freezes the simulation tick loop.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, cast

from pydantic import SecretStr

from langchain_core.tools import StructuredTool
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from backend.core.config import LLM_PROVIDER
from backend.models.drone import DroneRole
from backend.mcp_server import bind_simulation, mcp
from backend.simulation import Simulation
from backend.utils.mesh import get_isolated_drones

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]

# LLM calls take several seconds — no value cycling faster than this.
AGENT_CYCLE_SECONDS: int = 8


# ── Agent memory ──────────────────────────────────────────────────────────────


@dataclass
class AgentMemory:
    """In-session memory for ARIA. Cleared on mission reset."""

    cleared_cells: set[tuple[int, int]] = field(default_factory=set)
    confirmed_survivors: list[dict[str, Any]] = field(default_factory=list)
    rescued_survivors: list[str] = field(default_factory=list)
    failed_paths: list[dict[str, Any]] = field(default_factory=list)
    relay_positions: list[tuple[int, int]] = field(default_factory=list)
    last_aftershock_tick: int = 0
    previous_leader_id: str | None = None


# ── LLM provider registry ─────────────────────────────────────────────────────
# Add a new provider by adding one entry — never touch build_llm() itself.

_LLM_REGISTRY: dict[str, Callable[[], BaseChatModel]] = {
    "gemini": lambda: ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
        temperature=0.3,
    ),
    "deepseek": lambda: ChatOpenAI(
        model="deepseek-chat",
        api_key=SecretStr(os.getenv("DEEPSEEK_API_KEY") or ""),
        base_url="https://api.deepseek.com",
        temperature=0.3,
    ),
    "openai": lambda: ChatOpenAI(model="gpt-4o-mini", temperature=0.3),
    "claude": lambda: ChatAnthropic(model_name="claude-haiku-4-5-20251001", temperature=0.3, timeout=None, stop=None),
}


def build_llm() -> BaseChatModel:
    key = LLM_PROVIDER.lower()
    if key not in _LLM_REGISTRY:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{key}'. Valid: {list(_LLM_REGISTRY)}"
        )
    return _LLM_REGISTRY[key]()


# ── Tool discovery ────────────────────────────────────────────────────────────


async def build_tools() -> list[StructuredTool]:
    """
    Auto-discover all @mcp.tool() functions and wrap them as LangChain tools.

    bind_simulation() must be called before any tool is invoked.
    Adding a new tool to mcp_server.py is automatically picked up here.
    """
    mcp_tools = await mcp.list_tools()
    return [
        StructuredTool.from_function(
            func=cast(Any, tool).fn,
            name=tool.name,
            description=tool.description or "",
        )
        for tool in mcp_tools
    ]


# ── System prompt ─────────────────────────────────────────────────────────────
# No template variables needed — langgraph injects tool definitions automatically.

_ARIA_SYSTEM_PROMPT = """\
You are ARIA (Autonomous Rescue Intelligence Agent), coordinating a drone swarm \
in a post-disaster zone with NO cloud connectivity.

## Hard constraints (never violate these)
- ALWAYS call list_active_drones() at the start of every cycle — never hardcode drone IDs.
- ALWAYS call get_mission_status() at the start of every cycle.
- ALWAYS check battery via get_battery_status() before assigning a long mission.
- NEVER dispatch a Medic unless at least 2 Scout deep_scans confirm a survivor \
  (confidence > 0.7 each).
- ALWAYS maintain at least 1 relay drone deployed if any Scout is more than 8 cells \
  from base. Use get_mission_status() to check isolated drones.
- Prioritise CRITICAL condition survivors over STABLE.
- If a cell has been scanned with confidence > 0.9 and no survivor found, \
  consider it cleared and do not rescan.

## Chain-of-thought format
For EVERY cycle reason step-by-step using this exact format before acting:

OBSERVE: [Summarise current map state — phase, drones online, survivor status, threats]
ASSESS:  [Identify risks, coverage gaps, battery concerns, isolated drones, active fires]
DECIDE:  [Priority-ordered action list with a one-line reason for each]
EXECUTE: [Call the required tools]\
"""


# ── State summariser ──────────────────────────────────────────────────────────


def _build_context(sim: Simulation, memory: AgentMemory) -> str:
    """Compress simulation state into a compact string for the agent's input."""
    m = sim.mission
    drones = list(sim.drones.values())
    leader = next((d for d in drones if d.leader), None)

    # Leader change warning
    leader_warning = ""
    if leader and leader.id != memory.previous_leader_id and memory.previous_leader_id:
        leader_warning = (
            f"\n⚠️ LEADER CHANGED: {memory.previous_leader_id} → {leader.id}. Replan."
        )
    if leader:
        memory.previous_leader_id = leader.id

    drone_lines = [
        f"  {d.id} ({d.role.value}) battery={d.battery:.0f}% "
        f"pos=({d.x},{d.y}) status={d.status.value} alt={d.altitude}"
        for d in drones
    ]
    sv_lines = [
        f"  {s.id} at ({s.x},{s.y}) {s.condition.value} "
        f"[{'RESCUED' if s.rescued else 'DETECTED' if s.detected else 'UNKNOWN'}] "
        f"confirmed_by={s.confirmed_by}"
        for s in m.survivors
    ]

    isolated = [d.id for d in get_isolated_drones(drones)]
    top_prob = sim.query_mission_status().get("top_probability_cells", [])[:3]

    parts = [
        f"Phase: {m.phase.value} | Tick: {m.tick} | Coverage: {m.coverage_percent}%",
        f"Survivors: {m.survivors_rescued}/{m.survivors_total} rescued, "
        f"{m.survivors_detected} detected",
        f"Leader: {leader.id + f' (bat={leader.battery:.0f}%)' if leader else 'none'}",
        f"Isolated: {isolated or 'none'}",
        f"Top probability cells: {top_prob}",
        "", "Drones:", *drone_lines,
        "", "Survivors:", *sv_lines,
    ]
    if memory.confirmed_survivors:
        parts += ["", f"Confirmed awaiting medic: {memory.confirmed_survivors}"]
    if memory.relay_positions:
        parts += [f"Relay positions: {memory.relay_positions}"]
    if leader_warning:
        parts.append(leader_warning)

    return "\n".join(parts)


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _emit_thought(broadcast: BroadcastFn, phase: str, text: str) -> None:
    await broadcast({"event": "agent_thought", "data": {"phase": phase, "text": text}})


def _sync_memory(sim: Simulation, memory: AgentMemory) -> None:
    """Keep agent memory in sync with ground-truth simulation state."""
    for survivor in sim.mission.survivors:
        if survivor.rescued and survivor.id not in memory.rescued_survivors:
            memory.rescued_survivors.append(survivor.id)

    memory.confirmed_survivors = [
        s for s in memory.confirmed_survivors
        if s.get("id") not in memory.rescued_survivors
    ]
    memory.relay_positions = [
        (d.x, d.y) for d in sim.drones.values() if d.role == DroneRole.RELAY
    ]


def _format_args(args: dict | str) -> str:
    if isinstance(args, str):
        return args
    return ", ".join(f"{k}={v!r}" for k, v in args.items())


# ── Agent cycle ───────────────────────────────────────────────────────────────


async def _run_one_cycle(
    agent: Any,
    sim: Simulation,
    broadcast: BroadcastFn,
    memory: AgentMemory,
) -> None:
    """Execute one full observe → plan → act → learn cycle."""
    _sync_memory(sim, memory)
    context = _build_context(sim, memory)

    await _emit_thought(broadcast, "OBSERVE", f"Tick {sim.mission.tick} — analysing...")

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=context)]},
        version="v2",
        config={"recursion_limit": 12},
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content
            if chunk:
                await _emit_thought(broadcast, "THINKING", chunk)
        elif kind == "on_tool_start":
            name = event.get("name", "tool")
            args = event["data"].get("input", {})
            await _emit_thought(broadcast, "EXECUTE", f"→ {name}({_format_args(args)})")
        elif kind == "on_tool_end":
            result = str(event["data"].get("output", ""))[:200]
            await _emit_thought(broadcast, "RESULT", result)

    await _emit_thought(broadcast, "CYCLE_END", f"Cycle complete. Next in {AGENT_CYCLE_SECONDS}s.")


# ── Main loop ─────────────────────────────────────────────────────────────────


async def run_agent_loop(sim: Simulation, broadcast: BroadcastFn) -> None:
    """
    ARIA's main loop — runs as an independent asyncio task.

    Waits for the mission to become active, then cycles through
    observe → plan → act.
    Runs forever until mission ends.
    """
    while not sim.mission.active:
        await asyncio.sleep(1.0)

    logger.info("ARIA agent starting.")
    await _emit_thought(broadcast, "INIT", "ARIA online. Binding to simulation...")

    bind_simulation(sim)

    # Build LLM and tools
    try:
        llm = build_llm()
        tools = await build_tools()
    except Exception as exc:
        logger.error("ARIA failed to initialise: %s", exc)
        await _emit_thought(broadcast, "ERROR", f"Initialisation failed: {exc}")
        return

    # Create the ReAct agent (handle tool loop natively)
    agent = create_react_agent(llm, tools, prompt=SystemMessage(content=_ARIA_SYSTEM_PROMPT))
    memory = AgentMemory()

    await _emit_thought(broadcast, "INIT", f"ARIA ready. Provider: {LLM_PROVIDER}. Tools: {len(tools)}.")

    # Main loop: if mission is active, run one cycle every <AGENT_CYCLE_SECONDS>
    while sim.mission.active:
        try:
            await _run_one_cycle(agent, sim, broadcast, memory)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Agent cycle error: %s", exc)
            await _emit_thought(broadcast, "ERROR", f"Cycle error: {exc}")

        await asyncio.sleep(AGENT_CYCLE_SECONDS)

    await _emit_thought(broadcast, "COMPLETE", "Mission ended. ARIA standing down.")
    logger.info("ARIA agent loop ended.")
