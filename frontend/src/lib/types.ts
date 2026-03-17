// ── Enums (mirror backend Python enums exactly) ───────────────────────────

export type Terrain = 'OPEN' | 'DEBRIS' | 'RUBBLE' | 'WATER'

export type DroneRole = 'SCOUT' | 'MEDIC' | 'RELAY' | 'HEAVY'

export type DroneStatus =
  | 'IDLE'
  | 'MOVING'
  | 'SCANNING'
  | 'DELIVERING'
  | 'RETURNING'
  | 'CHARGING'
  | 'OFFLINE'

export type AltitudeState = 'CRUISING' | 'SCANNING' | 'DELIVERING' | 'RETURNING'

export type MissionPhase =
  | 'IDLE'
  | 'DEPLOYMENT'
  | 'SEARCH'
  | 'CONVERGENCE'
  | 'CONFIRMATION'
  | 'RESCUE'
  | 'EXTRACT'
  | 'COMPLETE'

export type SurvivorCondition = 'STABLE' | 'CRITICAL' | 'RESCUED' | 'UNKNOWN'

export type ScenarioKey = 'EARTHQUAKE_ALPHA' | 'TYPHOON_BETA' | 'STRESS_TEST'

// ── Core models (mirror backend .to_dict() output) ────────────────────────

export interface Cell {
  x: number
  y: number
  terrain: Terrain
  fire: boolean
  fire_intensity: number
  debris_level: number
  survivor: boolean
  survivor_id: string | null
  survivor_condition: SurvivorCondition
  searched: boolean
  search_confidence: number
  probability: number
  passable: boolean
}

export interface Drone {
  id: string
  role: DroneRole
  x: number
  y: number
  battery: number
  status: DroneStatus
  payload: string | null
  communication_range: number
  scan_radius: number
  path: [number, number][]
  target: [number, number] | null
  mission_id: string | null
  leader: boolean
  altitude: number
  altitude_state: AltitudeState
}

export interface Survivor {
  id: string
  x: number
  y: number
  condition: SurvivorCondition
  detected: boolean
  rescued: boolean
  detected_tick: number
  rescued_tick: number
  confirmed_by: string[]
}

export interface MissionStatus {
  scenario: ScenarioKey
  phase: MissionPhase
  tick: number
  active: boolean
  paused: boolean
  coverage_percent: number
  survivors_total: number
  survivors_detected: number
  survivors_rescued: number
}

// ── WebSocket event types ─────────────────────────────────────────────────

export interface WsInitEvent {
  event: 'init'
  data: {
    grid: { grid_size: number; cells: Cell[][] }
    drones: Drone[]
    survivors: Survivor[]
    mission: MissionStatus
    heatmap: number[][]
  }
}

export interface WsTickEvent {
  event: 'tick'
  data: {
    grid_delta: Cell[]
    drones: Drone[]
    mission: MissionStatus
  }
}

export interface WsDroneAltitudeEvent {
  event: 'drone_altitude'
  data: { drone_id: string; altitude: number; state: AltitudeState }
}

export interface WsSurvivorFoundEvent {
  event: 'survivor_found'
  data: { x: number; y: number; condition: SurvivorCondition }
}

export interface WsAidDeliveredEvent {
  event: 'aid_delivered'
  data: { survivor_id: string; drone_id: string }
}

export interface WsFireSpreadEvent {
  event: 'fire_spread'
  data: { new_fire_cells: [number, number][] }
}

export interface WsAftershockEvent {
  event: 'aftershock'
  data: { affected_cells: [number, number][] }
}

export interface WsPhaseChangeEvent {
  event: 'phase_change'
  data: { from: MissionPhase; to: MissionPhase; tick: number }
}

export interface WsLeaderChangedEvent {
  event: 'leader_changed'
  data: { old: string; new: string }
}

export interface WsAgentThoughtEvent {
  event: 'agent_thought'
  data: { phase: string; text: string }
}

export type WsEvent =
  | WsInitEvent
  | WsTickEvent
  | WsDroneAltitudeEvent
  | WsSurvivorFoundEvent
  | WsAidDeliveredEvent
  | WsFireSpreadEvent
  | WsAftershockEvent
  | WsPhaseChangeEvent
  | WsLeaderChangedEvent
  | WsAgentThoughtEvent

// ── Overlay modes ─────────────────────────────────────────────────────────

export type OverlayMode = 'none' | 'heatmap' | 'risk' | 'coverage'

// ── Agent log entry ───────────────────────────────────────────────────────

export interface AgentLogEntry {
  id: number
  timestamp: number
  phase: string
  text: string
}
