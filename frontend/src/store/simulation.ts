/**
 * Zustand store — single source of truth for all simulation state.
 * Updated exclusively by useSimulation (WebSocket events).
 * Components read from here; they never mutate directly.
 */
import { create } from 'zustand'
import type {
  Cell,
  Drone,
  Survivor,
  MissionStatus,
  AgentLogEntry,
} from '@/lib/types'

const GRID_SIZE = 30

function emptyGrid(): Cell[][] {
  return Array.from({ length: GRID_SIZE }, (_, y) =>
    Array.from({ length: GRID_SIZE }, (_, x) => ({
      x,
      y,
      terrain: 'OPEN' as const,
      fire: false,
      fire_intensity: 0,
      debris_level: 0,
      survivor: false,
      survivor_id: null,
      survivor_condition: 'UNKNOWN' as const,
      searched: false,
      search_confidence: 0,
      probability: 0,
      passable: true,
    })),
  )
}

export interface SimulationState {
  // Connection
  connected: boolean
  setConnected: (v: boolean) => void

  // Core state
  grid: Cell[][]
  drones: Drone[]
  survivors: Survivor[]
  mission: MissionStatus | null
  heatmap: number[][]

  // Agent log
  agentLog: AgentLogEntry[]
  nextLogId: number

  // Setters — called by useSimulation
  initState: (
    grid: Cell[][],
    drones: Drone[],
    survivors: Survivor[],
    mission: MissionStatus,
    heatmap: number[][],
  ) => void
  applyTickDelta: (
    changedCells: Cell[],
    drones: Drone[],
    mission: MissionStatus,
  ) => void
  updateDroneAltitude: (droneId: string, altitude: number) => void
  markSurvivorFound: (x: number, y: number) => void
  appendAgentLog: (phase: string, text: string) => void
  resetState: () => void
}

export const useSimStore = create<SimulationState>((set, get) => ({
  connected: false,
  setConnected: (v) => set({ connected: v }),

  grid: emptyGrid(),
  drones: [],
  survivors: [],
  mission: null,
  heatmap: Array.from({ length: GRID_SIZE }, () => Array(GRID_SIZE).fill(0)),
  agentLog: [],
  nextLogId: 0,

  initState: (grid, drones, survivors, mission, heatmap) =>
    set({ grid, drones, survivors, mission, heatmap, agentLog: [], nextLogId: 0 }),

  applyTickDelta: (changedCells, drones, mission) =>
    set((state) => {
      const newGrid = state.grid.map((row) => [...row])
      for (const cell of changedCells) {
        newGrid[cell.y][cell.x] = cell
      }
      return { grid: newGrid, drones, mission }
    }),

  updateDroneAltitude: (droneId, altitude) =>
    set((state) => ({
      drones: state.drones.map((d) =>
        d.id === droneId ? { ...d, altitude } : d,
      ),
    })),

  markSurvivorFound: (x, y) =>
    set((state) => {
      const newGrid = state.grid.map((row) => [...row])
      const cell = newGrid[y][x]
      newGrid[y][x] = { ...cell, survivor: true }
      return { grid: newGrid }
    }),

  appendAgentLog: (phase, text) => {
    const { nextLogId } = get()
    set((state) => ({
      agentLog: [
        ...state.agentLog,
        { id: nextLogId, timestamp: Date.now(), phase, text },
      ].slice(-200), // keep last 200 entries
      nextLogId: nextLogId + 1,
    }))
  },

  resetState: () =>
    set({
      grid: emptyGrid(),
      drones: [],
      survivors: [],
      mission: null,
      heatmap: Array.from({ length: GRID_SIZE }, () => Array(GRID_SIZE).fill(0)),
      agentLog: [],
      nextLogId: 0,
    }),
}))
