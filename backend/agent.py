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
from langgraph.prebuilt import create_react_agent  # noqa: PLC0415

from backend.core.config import LLM_PROVIDER, BASE_X, BASE_Y
from backend.models.drone import DroneRole
from backend.mcp_server import bind_simulation, mcp
from backend.simulation import Simulation
from backend.utils.mesh import get_isolated_drones

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]

# LLM calls take several seconds; sleep is dead time between cycles.
AGENT_CYCLE_SECONDS: int = 3


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
You are ARIA, coordinating a rescue drone swarm in a post-disaster zone.

## CRITICAL — No status queries, EVER
The human message already contains ALL state you need. \
NEVER call list_active_drones, get_mission_status, get_drone_status, get_battery_status, \
get_heatmap, or get_map_state. Every such call wastes a tool slot and adds dead time. \
If you find yourself about to call one, stop — the answer is already in the context.

## CRITICAL — Never interrupt a MOVING drone
If a drone shows status=MOVING, do NOT issue it any command. \
Only act on drones explicitly listed in ⚠️ SCAN NOW or ⚠️ MOVE NOW directives. \
If neither directive appears, output OBSERVE + "No IDLE drones." and stop.

## Action priority (execute every cycle, IDLE drones only)
1. **⚠️ SCAN NOW**: call thermal_scan, then immediately call move_to the listed target.
2. **⚠️ MOVE NOW**: call move_to the listed coordinate. Do NOT thermal_scan.
3. After thermal_scan confidence > 0.3: broadcast_finding, then request_confirmation.
4. After 2 independent deep_scan confirmations (confidence > 0.7): dispatch_medic.
5. Battery < 25%: return_to_base immediately (overrides everything else).

## Relay drones — ONLY act on ⚠️ RELAY NOW
When ⚠️ RELAY NOW appears, call deploy_relay with the exact coordinate shown. \
If ⚠️ RELAY NOW is NOT in the context, do NOT touch the relay drone at all — not with \
deploy_relay, not with move_to. A relay that is already MOVING must not be interrupted.

## Hard constraints
- NEVER dispatch Medic without 2 independent deep_scan confirmations (confidence > 0.7).
- NEVER rescan a cell already at confidence > 0.9.
- Prioritise CRITICAL survivors over STABLE.

## Format (strictly one OBSERVE line, then EXECUTE or "No IDLE drones.")
OBSERVE: [phase | tick | lowest-coverage quadrant | IDLE drones listed]
EXECUTE: [tool calls — one per IDLE drone listed in directives]\
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
        + (f" → ({d.target[0]},{d.target[1]}) eta≈{len(d.path)}t" if d.target and d.path else "")
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

    # Sample unsearched passable cells across the grid for concrete move targets
    rows = len(sim.grid)
    cols = len(sim.grid[0]) if rows else 0

    # Quadrant coverage — tells the agent which regions are unexplored
    half_r, half_c = rows // 2, cols // 2

    def _quad_cov(yr_start: int, yr_end: int, xr_start: int, xr_end: int) -> int:
        total = (yr_end - yr_start) * (xr_end - xr_start)
        if not total:
            return 0
        found = sum(
            1 for gy in range(yr_start, yr_end)
            for gx in range(xr_start, xr_end)
            if sim.grid[gy][gx].searched
        )
        return round(100 * found // total)

    quad_summary = (
        f"Quadrant coverage — NW:{_quad_cov(0,half_r,0,half_c)}% "
        f"NE:{_quad_cov(0,half_r,half_c,cols)}% "
        f"SW:{_quad_cov(half_r,rows,0,half_c)}% "
        f"SE:{_quad_cov(half_r,rows,half_c,cols)}%"
    )

    step = max(1, cols // 6)
    spread_targets: list[tuple[int, int]] = []
    for gy in range(0, rows, step):
        for gx in range(0, cols, step):
            cell = sim.grid[gy][gx]
            if not cell.searched and cell.passable and not cell.fire:
                spread_targets.append((gx, gy))
    if not spread_targets:
        spread_targets = [(p[1], p[2]) for p in top_prob] if top_prob else [(cols // 2, rows // 2)]

    # Drones that can scan — only if current cell has never been searched
    must_scan = [
        d.id for d in drones
        if d.status.value == "IDLE"
        and d.battery > 20
        and d.scan_radius > 0
        and not sim.grid[d.y][d.x].searched
    ]
    # All other IDLE drones need to relocate (already-searched cell, or relay)
    must_move_drones = [
        d for d in drones
        if d.status.value == "IDLE"
        and d.battery > 20
        and d.id not in must_scan
    ]

    parts = [
        f"Phase: {m.phase.value} | Tick: {m.tick} | Coverage: {m.coverage_percent}%",
        quad_summary,
        f"Survivors: {m.survivors_rescued}/{m.survivors_total} rescued, "
        f"{m.survivors_detected} detected",
        f"Leader: {leader.id + f' (bat={leader.battery:.0f}%)' if leader else 'none'}",
        f"Isolated: {isolated or 'none'}",
        f"Top probability cells: {top_prob}",
        "", "Drones:", *drone_lines,
        "", "Survivors:", *sv_lines,
    ]
    def _pick_targets(
        drones_list: list,
        pool: list[tuple[int, int]],
    ) -> list[tuple[str, int, int]]:
        """
        Assign targets to drones with three priorities:
        1. Least-covered quadrant first (spread coverage).
        2. Fewest drones already assigned to that quadrant this cycle (diversify).
        3. NEAREST target in that quadrant (short paths reduce collision risk).
        High-probability cells override everything (survivor signal).
        """
        if not pool or not drones_list:
            return []

        def cell_qcov(px: int, py: int) -> int:
            yr0 = 0 if py < half_r else half_r
            yr1 = half_r if py < half_r else rows
            xr0 = 0 if px < half_c else half_c
            xr1 = half_c if px < half_c else cols
            return _quad_cov(yr0, yr1, xr0, xr1)

        def cell_qlabel(px: int, py: int) -> str:
            return ("N" if py < half_r else "S") + ("W" if px < half_c else "E")

        available = list(pool)
        assigned_quads: list[str] = []
        result: list[tuple[str, int, int]] = []

        for d in drones_list:
            if not available:
                available = list(pool)
            drone_id = d.id if hasattr(d, "id") else str(d)
            dx, dy = (d.x, d.y) if hasattr(d, "x") else (0, 0)

            def score(idx: int) -> tuple:
                px, py = available[idx]
                prob = sim.grid[py][px].probability
                # If there's a strong survivor signal, jump to it immediately
                if prob > 0.4:
                    return (-1, 0, 0, -prob)
                qcov = cell_qcov(px, py)
                ql = cell_qlabel(px, py)
                already = assigned_quads.count(ql)
                dist = abs(px - dx) + abs(py - dy)
                # Lower = better: least-covered quad, fewest assigned, nearest
                return (qcov, already, dist, -prob)

            best_i = min(range(len(available)), key=score)
            tx, ty = available.pop(best_i)
            assigned_quads.append(cell_qlabel(tx, ty))
            result.append((drone_id, tx, ty))

        return result

    if must_scan:
        scan_drone_objs = [d for d in drones if d.id in must_scan]
        # Exclude each drone's own cell — after scanning it becomes searched
        # and move_to the same cell returns "No path to target"
        standing_cells = {(d.x, d.y) for d in scan_drone_objs}
        scan_pool = [t for t in spread_targets if t not in standing_cells] or spread_targets
        scan_assignments = _pick_targets(scan_drone_objs, scan_pool)
        scan_lines = [
            f"  {did}: thermal_scan → then move_to({tx}, {ty})"
            for did, tx, ty in scan_assignments
        ]
        parts += ["", "⚠️ SCAN NOW (then immediately move to listed target):"] + scan_lines
    if must_move_drones:
        standing_cells_move = {(d.x, d.y) for d in must_move_drones}
        move_pool = [t for t in spread_targets if t not in standing_cells_move] or spread_targets
        move_assignments = _pick_targets(must_move_drones, move_pool)
        move_lines = [
            f"  {did} → move_to({tx}, {ty})"
            for did, tx, ty in move_assignments
        ]
        parts += ["", "⚠️ MOVE NOW (cells already scanned — do NOT thermal_scan):"] + move_lines

    # Compute explicit relay target: midpoint between base and the farthest active scout
    idle_relays = [
        d for d in drones
        if d.role == DroneRole.RELAY and d.status.value == "IDLE" and d.battery > 20
    ]
    if idle_relays:
        active_scouts = [
            d for d in drones
            if d.role == DroneRole.SCOUT
            and d.status.value in ("MOVING", "IDLE", "SCANNING")
        ]
        if active_scouts:
            furthest = max(
                active_scouts,
                key=lambda d: abs(d.x - BASE_X) + abs(d.y - BASE_Y),
            )
            tx = (BASE_X + furthest.x) // 2
            ty = (BASE_Y + furthest.y) // 2
            relay_lines = [f"  {d.id} → deploy_relay({tx}, {ty})" for d in idle_relays]
            parts += [
                "",
                "⚠️ RELAY NOW (position relay midway between base and furthest scout — use deploy_relay):",
                *relay_lines,
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

    thinking_buffer = ""

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=context)]},
        version="v2",
        config={"recursion_limit": 20},
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content
            if chunk:
                thinking_buffer += chunk
        elif kind == "on_tool_start":
            if thinking_buffer.strip():
                await _emit_thought(broadcast, "THINKING", thinking_buffer.strip())
                thinking_buffer = ""
            name = event.get("name", "tool")
            args = event["data"].get("input", {})
            await _emit_thought(broadcast, "EXECUTE", f"→ {name}({_format_args(args)})")
        elif kind == "on_tool_end":
            result = str(event["data"].get("output", ""))[:200]
            await _emit_thought(broadcast, "RESULT", result)

    if thinking_buffer.strip():
        await _emit_thought(broadcast, "THINKING", thinking_buffer.strip())

    await _emit_thought(broadcast, "CYCLE_END", f"Cycle complete. Next in {AGENT_CYCLE_SECONDS}s.")


# ── Main loop ─────────────────────────────────────────────────────────────────


async def run_agent_loop(sim: Simulation, broadcast: BroadcastFn) -> None:
    """
    ARIA's main loop — runs as an independent asyncio task.

    Waits for the mission to become active, then cycles through
    observe → plan → act. Loops back to waiting after each mission ends
    so that reset → start cycles work without restarting the server.
    """
    bind_simulation(sim)

    # Build LLM and tools once — survive across mission resets.
    try:
        llm = build_llm()
        tools = await build_tools()
    except Exception as exc:
        logger.error("ARIA failed to initialise: %s", exc)
        sim.pause()
        await _emit_thought(
            broadcast,
            "ERROR",
            f"Initialisation failed: {exc}. Simulation paused — fix your API key and restart.",
        )
        return

    agent = create_react_agent(llm, tools, prompt=SystemMessage(content=_ARIA_SYSTEM_PROMPT))
    await _emit_thought(broadcast, "INIT", f"ARIA ready. Provider: {LLM_PROVIDER}. Tools: {len(tools)}.")

    while True:  # outer loop: survive mission resets
        # Wait for the next mission start
        while not sim.mission.active:
            await asyncio.sleep(1.0)

        logger.info("ARIA agent starting mission cycle.")
        await _emit_thought(broadcast, "INIT", "ARIA online.")

        memory = AgentMemory()

        while sim.mission.active:
            try:
                await _run_one_cycle(agent, sim, broadcast, memory)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Agent cycle error: %s", exc)
                await _emit_thought(broadcast, "ERROR", f"Cycle error: {exc}")

            await asyncio.sleep(AGENT_CYCLE_SECONDS)

        await _emit_thought(broadcast, "COMPLETE", "Mission ended. ARIA standing by.")
        logger.info("ARIA mission cycle complete.")
