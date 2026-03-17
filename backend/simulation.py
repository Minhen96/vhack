from __future__ import annotations

import asyncio
import json
import logging
import math
import random
from pathlib import Path
from typing import Callable, Awaitable

from backend.core.config import (
    GRID_SIZE,
    TICK_RATE,
    BASE_X,
    BASE_Y,
    BATTERY_DRAIN,
    BATTERY_RETURN_BUFFER,
    BATTERY_CHARGE_RATE,
    SCAN_ALTITUDE_BONUS,
    ALTITUDE_SCANNING,
    FIRE_SPREAD_CHANCE,
    FIRE_BURNOUT_TICKS,
    FIRE_BURNOUT_CHANCE,
    SURVIVOR_DETERIORATION_TICKS,
    AFTERSHOCK_INTERVAL,
    AFTERSHOCK_CELLS,
    PROB_CONVERGENCE,
    PROB_CONFIRMATION,
)
from backend.models.grid import Cell, Terrain
from backend.models.drone import Drone, DroneRole, DroneStatus, AltitudeState
from backend.models.mission import Mission, MissionPhase, Survivor, SurvivorCondition, ScenarioKey
from backend.utils.pathfinding import find_path
from backend.utils.heatmap import (
    update_on_detection,
    decay_all,
    mark_cleared,
    get_highest_probability_cells,
)
from backend.utils.mesh import compute_mesh_health, get_isolated_drones

logger = logging.getLogger(__name__)

# Broadcast callback type: receives a dict event and sends it to all WS clients
BroadcastFn = Callable[[dict], Awaitable[None]]

_SCENARIOS_PATH = Path(__file__).parent.parent / "scenarios" / "presets.json"


class Simulation:
    """
    Core simulation engine.

    All state lives here. The agent and frontend are consumers only —
    they never mutate state directly; everything goes through methods.
    """

    def __init__(self) -> None:
        self.grid: list[list[Cell]] = []
        self.drones: dict[str, Drone] = {}
        self.mission: Mission = Mission()
        self._broadcast: BroadcastFn | None = None
        self._tick_task: asyncio.Task | None = None

    # ── Public setup ──────────────────────────────────────────────────────────

    def set_broadcast(self, fn: BroadcastFn) -> None:
        """Register the WebSocket broadcast callback."""
        self._broadcast = fn

    def load_scenario(self, scenario_key: str | ScenarioKey) -> None:
        """Load scenario config and initialise grid + drones."""
        key = ScenarioKey(scenario_key)  # validates and normalises the value

        with _SCENARIOS_PATH.open() as f:
            presets = json.load(f)

        if key.value not in presets:
            raise ValueError(f"Unknown scenario: {key.value}")

        cfg = presets[key.value]
        survivors = self._init_grid(cfg)
        self._init_drones(cfg)
        self.mission = Mission(
            scenario=key,
            phase=MissionPhase.IDLE,
            total_cells=cfg["grid_size"] ** 2,
            survivors=survivors,
        )
        logger.info("Scenario '%s' loaded. Survivors placed: %d", scenario_key, len(survivors))

    def start(self) -> asyncio.Task:
        """Start the simulation tick loop as an independent asyncio task."""
        self.mission.active = True
        self.mission.paused = False
        self.mission.phase = MissionPhase.DEPLOYMENT
        self._tick_task = asyncio.create_task(self._tick_loop())
        logger.info("Simulation started.")
        return self._tick_task

    def pause(self) -> None:
        self.mission.paused = True

    def resume(self) -> None:
        self.mission.paused = False

    def stop(self) -> None:
        self.mission.active = False
        if self._tick_task:
            self._tick_task.cancel()

    # ── Tick loop ─────────────────────────────────────────────────────────────

    async def _tick_loop(self) -> None:
        while self.mission.active:
            if not self.mission.paused:
                await self._process_tick()
            await asyncio.sleep(1.0 / TICK_RATE)

    async def _process_tick(self) -> None:
        self.mission.tick += 1
        tick = self.mission.tick

        dirty_cells: set[tuple[int, int]] = set()
        dirty_drones: set[str] = set()
        events: list[dict] = []

        # 1. Move drones one step along their paths
        moved_drones = self._step_drone_positions()
        dirty_drones.update(moved_drones)

        # 2. Drain battery for moved drones; charge drones at base
        self._update_battery(moved_drones, dirty_drones)

        # 3. Transition drone altitudes toward their target
        altitude_events = self._step_drone_altitudes()
        events.extend(altitude_events)
        dirty_drones.update(e["data"]["drone_id"] for e in altitude_events)

        # 4. Fire spread and burnout
        fire_dirty, fire_events = self._update_fire()
        dirty_cells.update(fire_dirty)
        events.extend(fire_events)

        # 5. Aftershock
        if (
            self.mission.phase not in (MissionPhase.IDLE, MissionPhase.COMPLETE)
            and tick - self.mission.last_aftershock_tick >= AFTERSHOCK_INTERVAL
            and tick > 0
        ):
            shock_dirty, shock_events = self._trigger_aftershock()
            dirty_cells.update(shock_dirty)
            events.extend(shock_events)
            self.mission.last_aftershock_tick = tick

        # 6. Heatmap decay
        decay_all(self.grid)

        # 7. Survivor deterioration
        det_events = self._check_survivor_deterioration()
        events.extend(det_events)

        # 8. Phase transition check
        phase_events = self._check_phase_transitions()
        events.extend(phase_events)

        # 9. Broadcast tick delta
        await self._emit(
            {
                "event": "tick",
                "data": {
                    "tick": tick,
                    "mission": self.mission.to_dict(),
                    "grid_delta": [
                        self.grid[y][x].to_dict() for x, y in dirty_cells
                    ],
                    "drones": [
                        self.drones[did].to_dict()
                        for did in dirty_drones
                        if did in self.drones
                    ],
                },
            }
        )

        for event in events:
            await self._emit(event)

    # ── Drone movement ────────────────────────────────────────────────────────

    def _step_drone_positions(self) -> set[str]:
        """Advance each moving drone one cell along its planned path."""
        moved: set[str] = set()
        occupied = {(d.x, d.y) for d in self.drones.values()}

        for drone in self.drones.values():
            if drone.status != DroneStatus.MOVING or not drone.path:
                continue

            next_cell_coord = drone.path[0]
            nx, ny = next_cell_coord

            # Soft collision: skip this tick if next cell is occupied
            if next_cell_coord in occupied and next_cell_coord != (drone.x, drone.y):
                continue

            occupied.discard((drone.x, drone.y))
            drone.x, drone.y = nx, ny
            drone.path = drone.path[1:]
            occupied.add((nx, ny))
            moved.add(drone.id)

            if not drone.path:
                # Reached destination
                self._on_drone_arrived(drone)

        return moved

    def _on_drone_arrived(self, drone: Drone) -> None:
        """Called when a drone reaches the end of its path."""
        if drone.target == (BASE_X, BASE_Y):
            drone.status = DroneStatus.CHARGING
            drone.altitude_state = AltitudeState.CRUISING
        else:
            if drone.status == DroneStatus.MOVING:
                drone.status = DroneStatus.IDLE
            drone.target = None

    # ── Battery ───────────────────────────────────────────────────────────────

    def _update_battery(
        self, moved_ids: set[str], dirty_drones: set[str]
    ) -> None:
        for drone in self.drones.values():
            if drone.id in moved_ids:
                drain = BATTERY_DRAIN[drone.role.value]
                drone.battery = max(0.0, drone.battery - drain)
                dirty_drones.add(drone.id)

                # Auto-return if battery critically low
                if self._should_return(drone) and drone.status not in (
                    DroneStatus.RETURNING,
                    DroneStatus.CHARGING,
                ):
                    self.command_return_to_base(drone.id)

            elif drone.status == DroneStatus.CHARGING:
                if drone.battery < 100.0:
                    drone.battery = min(100.0, drone.battery + BATTERY_CHARGE_RATE)
                    dirty_drones.add(drone.id)
                    if drone.battery >= 100.0:
                        drone.status = DroneStatus.IDLE

    def _should_return(self, drone: Drone) -> bool:
        dist = math.sqrt(
            (drone.x - BASE_X) ** 2 + (drone.y - BASE_Y) ** 2
        )
        needed = dist * drone.battery_drain_rate * BATTERY_RETURN_BUFFER
        return drone.battery <= needed

    # ── Altitude ──────────────────────────────────────────────────────────────

    def _step_drone_altitudes(self) -> list[dict]:
        events: list[dict] = []
        for drone in self.drones.values():
            changed = drone.step_altitude()
            if changed:
                events.append(
                    {
                        "event": "drone_altitude",
                        "data": {
                            "drone_id": drone.id,
                            "altitude": drone.altitude,
                            "state": drone.altitude_state.value,
                        },
                    }
                )
        return events

    # ── Fire dynamics ─────────────────────────────────────────────────────────

    def _update_fire(self) -> tuple[set[tuple[int, int]], list[dict]]:
        dirty: set[tuple[int, int]] = set()
        new_fire_cells: list[dict] = []

        rows = len(self.grid)
        cols = len(self.grid[0]) if rows else 0

        cells_to_spread: list[Cell] = []
        cells_to_check_burnout: list[Cell] = []

        for row in self.grid:
            for cell in row:
                if cell.fire:
                    cell.fire_age += 1
                    cells_to_spread.append(cell)
                    if cell.fire_age >= FIRE_BURNOUT_TICKS:
                        cells_to_check_burnout.append(cell)

        rng = random.Random()

        # Spread
        for cell in cells_to_spread:
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = cell.x + dx, cell.y + dy
                if not (0 <= nx < cols and 0 <= ny < rows):
                    continue
                neighbor = self.grid[ny][nx]
                if not neighbor.fire and neighbor.passable and neighbor.terrain != Terrain.WATER:
                    if rng.random() < FIRE_SPREAD_CHANCE:
                        neighbor.fire = True
                        neighbor.fire_age = 0
                        neighbor.fire_intensity = min(3, cell.fire_intensity)
                        neighbor.passable = True  # fire cells remain passable but penalised
                        dirty.add((nx, ny))
                        new_fire_cells.append({"x": nx, "y": ny})

        # Burnout
        for cell in cells_to_check_burnout:
            if rng.random() < FIRE_BURNOUT_CHANCE:
                cell.fire = False
                cell.fire_age = 0
                cell.fire_intensity = 0
                dirty.add((cell.x, cell.y))

        events: list[dict] = []
        if new_fire_cells:
            events.append({"event": "fire_spread", "data": {"new_fire_cells": new_fire_cells}})

        return dirty, events

    # ── Aftershock ────────────────────────────────────────────────────────────

    def _trigger_aftershock(self) -> tuple[set[tuple[int, int]], list[dict]]:
        dirty: set[tuple[int, int]] = set()
        affected: list[dict] = []
        rows = len(self.grid)
        cols = len(self.grid[0]) if rows else 0
        rng = random.Random(self.mission.tick)

        for _ in range(AFTERSHOCK_CELLS):
            x = rng.randint(0, cols - 1)
            y = rng.randint(0, rows - 1)
            cell = self.grid[y][x]
            if cell.terrain != Terrain.WATER and not cell.fire:
                cell.debris_level = min(3, cell.debris_level + 1)
                if cell.debris_level >= 2:
                    cell.terrain = Terrain.RUBBLE
                dirty.add((x, y))
                affected.append({"x": x, "y": y})

        events = [{"event": "aftershock", "data": {"affected_cells": affected}}]
        return dirty, events

    # ── Survivor deterioration ────────────────────────────────────────────────

    def _check_survivor_deterioration(self) -> list[dict]:
        events: list[dict] = []
        for survivor in self.mission.survivors:
            if survivor.detected and not survivor.rescued:
                survivor.time_since_detected = (
                    self.mission.tick - survivor.detected_tick
                )
                if (
                    survivor.condition == SurvivorCondition.STABLE
                    and survivor.time_since_detected >= SURVIVOR_DETERIORATION_TICKS
                ):
                    survivor.condition = SurvivorCondition.CRITICAL
                    cell = self.grid[survivor.y][survivor.x]
                    cell.survivor_condition = SurvivorCondition.CRITICAL.value
                    events.append(
                        {
                            "event": "survivor_deteriorated",
                            "data": {
                                "survivor_id": survivor.id,
                                "x": survivor.x,
                                "y": survivor.y,
                                "condition": SurvivorCondition.CRITICAL.value,
                            },
                        }
                    )
        return events

    # ── Phase transitions ─────────────────────────────────────────────────────

    def _check_phase_transitions(self) -> list[dict]:
        events: list[dict] = []
        phase = self.mission.phase
        new_phase: MissionPhase | None = None

        if phase == MissionPhase.DEPLOYMENT:
            # All drones have left base
            all_deployed = all(
                d.position != (BASE_X, BASE_Y) or d.status == DroneStatus.IDLE
                for d in self.drones.values()
            )
            if all_deployed:
                new_phase = MissionPhase.SEARCH

        elif phase == MissionPhase.SEARCH:
            max_prob = max(
                (cell.probability for row in self.grid for cell in row), default=0.0
            )
            if max_prob >= PROB_CONVERGENCE:
                new_phase = MissionPhase.CONVERGENCE

        elif phase == MissionPhase.CONVERGENCE:
            max_prob = max(
                (cell.probability for row in self.grid for cell in row), default=0.0
            )
            if max_prob >= PROB_CONFIRMATION:
                new_phase = MissionPhase.CONFIRMATION

        elif phase == MissionPhase.CONFIRMATION:
            has_confirmed = any(
                len(s.confirmed_by) >= 2 for s in self.mission.survivors if s.detected
            )
            if has_confirmed:
                new_phase = MissionPhase.RESCUE

        elif phase == MissionPhase.RESCUE:
            all_rescued = all(s.rescued for s in self.mission.survivors)
            all_low_battery = all(
                d.battery < 20 for d in self.drones.values()
            )
            if all_rescued or all_low_battery:
                new_phase = MissionPhase.EXTRACT

        elif phase == MissionPhase.EXTRACT:
            all_home = all(
                d.position == (BASE_X, BASE_Y) or d.status == DroneStatus.CHARGING
                for d in self.drones.values()
            )
            if all_home:
                new_phase = MissionPhase.COMPLETE
                self.mission.active = False

        if new_phase:
            old_phase = self.mission.phase
            self.mission.phase = new_phase
            events.append(
                {
                    "event": "phase_change",
                    "data": {
                        "from": old_phase.value,
                        "to": new_phase.value,
                        "tick": self.mission.tick,
                    },
                }
            )
            logger.info("Phase transition: %s → %s", old_phase.value, new_phase.value)

        return events

    # ── MCP-callable commands ─────────────────────────────────────────────────
    # These are the methods the MCP server calls. They validate input and
    # mutate simulation state, then return structured results.

    def command_move_to(
        self, drone_id: str, x: int, y: int
    ) -> dict:
        drone = self._get_drone(drone_id)
        rows = len(self.grid)
        cols = len(self.grid[0]) if rows else 0

        if not (0 <= x < cols and 0 <= y < rows):
            return {"success": False, "error": "Coordinates out of bounds."}

        target_cell = self.grid[y][x]
        if not target_cell.passable:
            return {"success": False, "error": "Target cell is not passable."}

        occupied = {
            (d.x, d.y) for d in self.drones.values() if d.id != drone_id
        }
        path = find_path(self.grid, drone.position, (x, y), occupied)

        if not path:
            return {"success": False, "error": "No path to target."}

        drone.path = path
        drone.target = (x, y)
        drone.status = DroneStatus.MOVING
        drone.altitude_state = AltitudeState.CRUISING

        return {"success": True, "eta_ticks": len(path), "path_length": len(path)}

    def command_thermal_scan(self, drone_id: str) -> dict:
        drone = self._get_drone(drone_id)
        if drone.scan_radius == 0:
            return {"success": False, "error": "This drone role cannot scan."}

        drone.status = DroneStatus.SCANNING
        drone.altitude_state = AltitudeState.SCANNING

        accuracy = drone.scan_accuracy
        if drone.altitude <= ALTITUDE_SCANNING:
            accuracy = min(1.0, accuracy + SCAN_ALTITUDE_BONUS)

        # Degrade accuracy in fire / heavy debris
        cell_at = self.grid[drone.y][drone.x]
        if cell_at.fire:
            accuracy *= 0.6
        elif cell_at.debris_level >= 2:
            accuracy *= 0.8

        rows = len(self.grid)
        cols = len(self.grid[0]) if rows else 0
        scan_results: dict[str, float] = {}
        detected_cells: list[dict] = []

        for dy in range(-drone.scan_radius, drone.scan_radius + 1):
            for dx in range(-drone.scan_radius, drone.scan_radius + 1):
                nx, ny = drone.x + dx, drone.y + dy
                if not (0 <= nx < cols and 0 <= ny < rows):
                    continue
                cell = self.grid[ny][nx]
                cell.last_scanned_tick = self.mission.tick
                cell.searched = True

                confidence = 0.0
                if cell.survivor:
                    confidence = accuracy * random.uniform(0.8, 1.0)
                    if confidence > 0.3:
                        if not cell.survivor_id:
                            continue
                        survivor = self._find_survivor(cell.survivor_id)
                        if survivor and not survivor.detected:
                            survivor.detected = True
                            survivor.detected_tick = self.mission.tick
                        update_on_detection(self.grid, nx, ny, confidence)
                        detected_cells.append(
                            {"x": nx, "y": ny, "confidence": round(confidence, 3)}
                        )
                else:
                    # Small false-signal chance
                    confidence = random.uniform(0, 0.05)
                    if confidence < 0.01:
                        mark_cleared(self.grid, nx, ny)

                cell.search_confidence = min(
                    1.0, cell.search_confidence + confidence * 0.5
                )
                scan_key = f"{nx},{ny}"
                scan_results[scan_key] = round(confidence, 3)

        self.mission.searched_cells = sum(
            1 for row in self.grid for cell in row if cell.searched
        )

        drone.status = DroneStatus.IDLE

        return {
            "success": True,
            "accuracy": round(accuracy, 3),
            "cells_scanned": scan_results,
            "detected": detected_cells,
        }

    def command_deep_scan(self, drone_id: str, x: int, y: int) -> dict:
        """Focused high-confidence scan of a single cell. Uses extra battery."""
        drone = self._get_drone(drone_id)
        rows, cols = len(self.grid), len(self.grid[0]) if self.grid else 0

        if not (0 <= x < cols and 0 <= y < rows):
            return {"success": False, "error": "Coordinates out of bounds."}

        drone.battery = max(0.0, drone.battery - 2.0)
        drone.altitude_state = AltitudeState.SCANNING

        cell = self.grid[y][x]
        cell.last_scanned_tick = self.mission.tick
        cell.searched = True

        confidence = 0.0
        if cell.survivor:
            confidence = min(1.0, drone.scan_accuracy + SCAN_ALTITUDE_BONUS + 0.1)
            survivor = self._find_survivor(cell.survivor_id)
            if survivor and not survivor.detected:
                survivor.detected = True
                survivor.detected_tick = self.mission.tick
            update_on_detection(self.grid, x, y, confidence)

            # Register this drone as a confirmer
            if survivor and drone_id not in survivor.confirmed_by:
                survivor.confirmed_by.append(drone_id)
        else:
            mark_cleared(self.grid, x, y)

        return {
            "success": True,
            "x": x,
            "y": y,
            "confidence": round(confidence, 3),
            "survivor_present": cell.survivor,
        }

    def command_return_to_base(self, drone_id: str) -> dict:
        drone = self._get_drone(drone_id)
        path = find_path(self.grid, drone.position, (BASE_X, BASE_Y))
        if not path:
            return {"success": False, "error": "No path to base."}

        drone.path = path
        drone.target = (BASE_X, BASE_Y)
        drone.status = DroneStatus.RETURNING
        drone.altitude_state = AltitudeState.RETURNING

        return {"success": True, "eta_ticks": len(path)}

    def command_deliver_aid(self, drone_id: str) -> dict:
        drone = self._get_drone(drone_id)

        if drone.altitude > 8:
            return {
                "success": False,
                "error": f"Drone altitude too high ({drone.altitude}). Must descend to 8 or below first.",
            }

        if drone.payload is None:
            return {"success": False, "error": "No payload to deliver."}

        cell = self.grid[drone.y][drone.x]
        if not cell.survivor:
            return {"success": False, "error": "No survivor at this cell."}

        survivor = self._find_survivor(cell.survivor_id)
        if survivor:
            survivor.rescued = True
            survivor.rescued_tick = self.mission.tick
            cell.survivor_condition = SurvivorCondition.RESCUED.value

        drone.payload = None
        drone.status = DroneStatus.IDLE
        drone.altitude_state = AltitudeState.CRUISING

        return {
            "success": True,
            "survivor_id": cell.survivor_id,
            "tick": self.mission.tick,
        }

    def command_dispatch_medic(
        self, drone_id: str, target_x: int, target_y: int
    ) -> dict:
        drone = self._get_drone(drone_id)
        if drone.role != DroneRole.MEDIC:
            return {"success": False, "error": "Only MEDIC drones can deliver aid."}
        if drone.payload is None:
            drone.payload = "MEDKIT"

        result = self.command_move_to(drone_id, target_x, target_y)
        if not result["success"]:
            return result

        drone.status = DroneStatus.DELIVERING
        drone.altitude_state = AltitudeState.DELIVERING
        return result

    def command_deploy_relay(self, x: int, y: int) -> dict:
        # Find an idle relay drone
        relay = next(
            (d for d in self.drones.values()
             if d.role == DroneRole.RELAY and d.status == DroneStatus.IDLE),
            None,
        )
        if relay is None:
            return {"success": False, "error": "No idle relay drone available."}

        return self.command_move_to(relay.id, x, y)

    # ── Read-only queries (used by MCP tools) ─────────────────────────────────

    def query_map_state(self) -> dict:
        return {
            "grid_size": len(self.grid),
            "cells": [[cell.to_dict() for cell in row] for row in self.grid],
        }

    def query_heatmap(self) -> list[list[float]]:
        return [
            [round(cell.probability, 3) for cell in row] for row in self.grid
        ]

    def query_drones(self) -> list[dict]:
        return [d.to_dict() for d in self.drones.values()]

    def query_drone(self, drone_id: str) -> dict:
        return self._get_drone(drone_id).to_dict()

    def query_survivors(self) -> list[dict]:
        return [s.to_dict() for s in self.mission.survivors]

    def query_mission_status(self) -> dict:
        return {
            **self.mission.to_dict(),
            "mesh_health": compute_mesh_health(list(self.drones.values())),
            "isolated_drones": [
                d.id for d in get_isolated_drones(list(self.drones.values()))
            ],
            "top_probability_cells": get_highest_probability_cells(self.grid),
        }

    # ── Map generation ────────────────────────────────────────────────────────

    def _init_grid(self, cfg: dict) -> list[Survivor]:
        """Build the grid and return a list of placed survivors."""
        size = cfg.get("grid_size", GRID_SIZE)
        disaster = cfg.get("disaster_type", "EARTHQUAKE")
        seed = cfg.get("seed", 42)
        rng = random.Random(seed)

        # Build blank grid
        self.grid = [
            [Cell(x=x, y=y) for x in range(size)]
            for y in range(size)
        ]

        if disaster == "EARTHQUAKE":
            self._gen_earthquake(rng, cfg)
        elif disaster == "TYPHOON":
            self._gen_typhoon(rng, cfg)
        elif disaster == "FIRE_DISASTER":
            self._gen_fire_disaster(rng, cfg)

        return self._place_survivors(
            rng=rng,
            count=cfg.get("survivors", 5),
        )

    def _gen_earthquake(self, rng: random.Random, cfg: dict) -> None:
        size = len(self.grid)
        density = cfg.get("debris_density", 0.30)
        fire_count = cfg.get("fire_start_cells", 3)

        # Debris clusters
        cluster_count = max(1, int(size * density / 5))
        for _ in range(cluster_count):
            cx, cy = rng.randint(0, size - 1), rng.randint(0, size - 1)
            radius = rng.randint(2, 5)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < size and 0 <= ny < size:
                        if rng.random() < density:
                            cell = self.grid[ny][nx]
                            level = rng.choices([1, 2, 3], weights=[5, 3, 2])[0]
                            cell.debris_level = level
                            cell.terrain = Terrain.RUBBLE if level >= 2 else Terrain.DEBRIS

        # Fire cells
        for _ in range(fire_count):
            x, y = rng.randint(0, size - 1), rng.randint(0, size - 1)
            cell = self.grid[y][x]
            if not cell.survivor:
                cell.fire = True
                cell.fire_intensity = rng.randint(1, 2)

    def _gen_typhoon(self, rng: random.Random, cfg: dict) -> None:
        size = len(self.grid)
        density = cfg.get("debris_density", 0.20)

        # Water zones — generate path first, then apply, avoiding mutable loop state
        water_patches = rng.randint(3, 6)
        for _ in range(water_patches):
            walk: list[tuple[int, int]] = [
                (rng.randint(0, size - 1), rng.randint(0, size - 1))
            ]
            for _ in range(rng.randint(10, 25) - 1):
                px, py = walk[-1]
                step_x, step_y = rng.choice([(0, 1), (0, -1), (1, 0), (-1, 0)])
                walk.append((
                    max(0, min(size - 1, px + step_x)),
                    max(0, min(size - 1, py + step_y)),
                ))
            for wx, wy in walk:
                self.grid[wy][wx].terrain = Terrain.WATER
                self.grid[wy][wx].passable = False

        # Scattered debris
        debris_count = int(size * size * density)
        for _ in range(debris_count):
            x, y = rng.randint(0, size - 1), rng.randint(0, size - 1)
            cell = self.grid[y][x]
            if cell.terrain != Terrain.WATER:
                cell.debris_level = rng.randint(1, 2)
                cell.terrain = Terrain.DEBRIS

    def _gen_fire_disaster(self, rng: random.Random, cfg: dict) -> None:
        size = len(self.grid)
        fire_count = cfg.get("fire_start_cells", 8)
        density = cfg.get("debris_density", 0.15)

        # Fire clusters
        for _ in range(fire_count):
            fx, fy = rng.randint(2, size - 3), rng.randint(2, size - 3)
            radius = rng.randint(1, 3)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    nx, ny = fx + dx, fy + dy
                    if 0 <= nx < size and 0 <= ny < size:
                        if rng.random() < 0.7:
                            cell = self.grid[ny][nx]
                            cell.fire = True
                            cell.fire_intensity = rng.randint(1, 3)

        # Light debris
        debris_count = int(size * size * density)
        for _ in range(debris_count):
            x, y = rng.randint(0, size - 1), rng.randint(0, size - 1)
            cell = self.grid[y][x]
            if not cell.fire:
                cell.debris_level = 1
                cell.terrain = Terrain.DEBRIS

    def _place_survivors(
        self,
        rng: random.Random,
        count: int,
    ) -> list[Survivor]:
        size = len(self.grid)
        survivors: list[Survivor] = []

        # Cluster centers — away from fires and water
        safe_cells = [
            (cell.x, cell.y)
            for row in self.grid
            for cell in row
            if cell.passable and not cell.fire and cell.debris_level < 3
        ]
        if not safe_cells:
            safe_cells = [(size // 2, size // 2)]

        cluster_count = max(1, count // 2)
        centers = rng.choices(safe_cells, k=cluster_count)

        placed = 0
        attempts = 0

        while placed < count and attempts < count * 50:
            attempts += 1
            cx, cy = rng.choice(centers)
            sigma = 4.0
            x = int(rng.gauss(cx, sigma))
            y = int(rng.gauss(cy, sigma))

            if not (0 <= x < size and 0 <= y < size):
                continue

            cell = self.grid[y][x]
            # Don't place survivor on fire, water, or already occupied cell
            if not cell.passable or cell.fire or cell.survivor:
                continue

            survivor_id = f"S{placed + 1}"
            cell.survivor = True
            cell.survivor_id = survivor_id
            condition = rng.choice([SurvivorCondition.STABLE, SurvivorCondition.STABLE, SurvivorCondition.CRITICAL])
            cell.survivor_condition = condition.value

            survivors.append(
                Survivor(
                    id=survivor_id,
                    x=x,
                    y=y,
                    condition=condition,
                )
            )
            placed += 1

        return survivors

    def _init_drones(self, cfg: dict) -> None:
        self.drones.clear()
        drone_config: dict[str, int] = cfg.get(
            "drones", {"SCOUT": 2, "MEDIC": 1, "RELAY": 1}
        )

        counters: dict[str, int] = {}
        first_scout = True

        for role_str, count in drone_config.items():
            role = DroneRole(role_str)
            counters[role_str] = 0
            for _ in range(count):
                counters[role_str] += 1
                drone_id = f"{role_str[0]}{counters[role_str]}"
                drone = Drone(
                    id=drone_id,
                    role=role,
                    x=BASE_X,
                    y=BASE_Y,
                )
                if role == DroneRole.SCOUT and first_scout:
                    drone.leader = True
                    first_scout = False
                self.drones[drone_id] = drone

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_drone(self, drone_id: str) -> Drone:
        if drone_id not in self.drones:
            raise KeyError(f"Drone '{drone_id}' not found.")
        return self.drones[drone_id]

    def _find_survivor(self, survivor_id: str | None) -> Survivor | None:
        if survivor_id is None:
            return None
        return next((s for s in self.mission.survivors if s.id == survivor_id), None)

    async def _emit(self, event: dict) -> None:
        if self._broadcast:
            try:
                await self._broadcast(event)
            except Exception:
                logger.exception("Failed to broadcast event: %s", event.get("event"))
