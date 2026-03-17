# CLAUDE.md — Project Standards & Preferences

## Core Principle
**Quality over speed, always.** Do not take shortcuts to ship faster.
A working, clean, correct implementation is worth more than a fast, brittle one.

---

## Python (Backend)

### Style
- Python 3.11+
- Type hints on every function signature — no bare `def foo(x):`
- Dataclasses or Pydantic models for all data structures — no raw dicts passed between functions
- `async`/`await` throughout — no blocking calls in async context
- Use `|` for union types (`str | None`, not `Optional[str]`)

### Structure
- One responsibility per file — do not dump unrelated logic together
- Keep functions small and named clearly — `update_drone_altitude()` not `update()`
- Constants go in a dedicated `constants.py`, not scattered as magic numbers
- No `print()` for debugging — use `logging` with proper levels

### Quality rules
- No bare `except:` — always catch specific exceptions
- No mutable default arguments (`def foo(items=[])`)
- Never silently swallow errors — log them at minimum
- All Pydantic models must have field validation where it makes sense
- FastAPI route handlers must be thin — logic lives in service/util modules, not in the route

### Example of what we want
```python
# Good
async def move_drone(drone_id: str, x: int, y: int) -> MoveResult:
    drone = get_drone_or_raise(drone_id)
    path = pathfinder.find_path(drone.position, (x, y))
    if not path:
        raise DronePathError(f"No path from {drone.position} to ({x}, {y})")
    drone.assign_path(path)
    return MoveResult(success=True, eta_ticks=len(path))

# Bad — do not do this
def move(id, x, y):
    try:
        d = drones[id]
        d.path = find_path(d.x, d.y, x, y)
        return {"ok": True}
    except:
        return {"ok": False}
```

---

## TypeScript / Next.js (Frontend)

### Style
- TypeScript strict mode — `"strict": true` in tsconfig
- No `any` — define proper types or interfaces
- All components must have typed props interfaces
- Use `const` by default, `let` only when reassignment is needed
- Prefer named exports over default exports for components

### React
- Functional components only — no class components
- Custom hooks for all reusable stateful logic (`useSimulation`, `useMapOverlay`)
- Keep components focused — if a component does too much, split it
- Avoid prop drilling more than 2 levels — use context or lift state
- `useEffect` dependencies must be correct and complete — no suppression comments

### Three.js / React Three Fiber
- Use `@react-three/drei` helpers instead of reimplementing common patterns
- All `useFrame` callbacks must be lightweight — heavy computation outside the render loop
- Dispose geometries and materials when components unmount
- Use instanced meshes for repeated objects (cells, debris tiles)

### Quality rules
- No `// @ts-ignore` or `// @ts-expect-error` without a comment explaining why
- No inline styles — use Tailwind classes
- No hardcoded magic numbers in components — extract as named constants
- API response types must match backend Pydantic models exactly

---

## General

### What to always do
- Separate concerns: data models, business logic, API layer, UI layer are distinct
- Write self-documenting code — variable and function names should make comments unnecessary
- When adding a new feature, check if existing utilities can be reused first
- Keep the simulation state as the single source of truth — frontend only renders, never mutates
- WebSocket events from backend drive all frontend state updates

### What to never do
- Never hardcode drone IDs, cell coordinates, or scenario values in logic code
- Never put business logic inside FastAPI route handlers or React components
- Never mix simulation tick logic with agent reasoning logic — they run independently
- Never use `setTimeout`/`sleep` as a substitute for proper async patterns
- Never skip error handling because "it won't happen in demo"

### Commits
- Commit working increments — do not commit broken code
- Commit message format: `[component] short description` e.g. `[simulation] add altitude state transitions`
- One logical change per commit

---

## Project-Specific Rules

- The simulation grid is the **single source of truth** — all state lives there
- The agent communicates with the simulation **only through MCP tool calls** — never direct function calls
- The 3D view reads from the same data as the 2D view — no separate 3D state
- `drone.altitude` is a real simulation field — do not hardcode altitude in the frontend
- Ground height in 3D is always derived from `cell.debris_level` — no hardcoded tile heights
- Agent loop and simulation tick loop must always run as separate `asyncio` tasks
