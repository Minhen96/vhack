import { create } from 'zustand';

// =============================================================================
// TypeScript Interfaces
// =============================================================================

/** 3D position coordinate */
export interface Position {
  x: number;
  y: number;
  z: number;
}

/** Spherical coordinate data from drone sensors */
export interface SphericalCoords {
  azimuth: number;
  elevation: number;
  fov: number;
  scan_radius: number;
  roll?: number;
}

/** Complete drone state from WebSocket messages */
export interface DroneState {
  drone_id: string;
  position: Position;
  spherical: SphericalCoords;
  status: DroneStatus;
  battery: number; // 0-100 percentage
  eta_ms: number;
  timestamp: number;
}

/** Survivor/thermal signature detection */
export interface Survivor {
  id: string;
  position: Position;
  confidence: number;
  status: SurvivorStatus;
  thermalSignature: boolean;
  timestamp: number;
  detected_by: string;
}

/** Blocked area from grid_snapshot (rubble/obstacle) */
export interface BlockedArea {
  x: number;
  y: number;
  radius: number;
}

/** Building obstacle from server */
export interface Building {
  id: string;
  x: number;
  y: number;     // ground plane Z (maps to Three.js Z)
  width: number;
  height: number;
  depth: number;
  thermal: number;
}

/** Grid snapshot containing all blocked areas */
export interface GridSnapshot {
  blocked: BlockedArea[];
  command_base?: {
    x: number;
    y: number;
  };
}

/** Connection status enum */
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

/** Drone operational status */
export type DroneStatus = 'SCANNING' | 'RETURNING' | 'IDLE' | 'SEARCHING';

/** Survivor status */
export type SurvivorStatus = 'TRAPPED' | 'DETECTED' | 'AID_SENT' | 'CONFIRMED' | 'RESCUED';

/** WebSocket message types */
type WebSocketMessageType =
  | 'init_connection'
  | 'send_position'
  | 'survivor_detected'
  | 'survivors_update'
  | 'grid_snapshot'
  | 'grid_update'
  | 'scan_heatmap'
  | 'drone_disconnected'
  | 'global_state_update'
  | 'dispatch_aid'
  | 'aid_delivered';

/** Raw WebSocket message from server */
interface WebSocketMessage {
  type: WebSocketMessageType;
  [key: string]: unknown;
}

// =============================================================================
// Store State Interface
// =============================================================================

interface DroneStore {
  // Connection state
  connectionStatus: ConnectionStatus;
  wsUrl: string;

  // Drones state - Map of drone_id to DroneState for multi-drone support
  drones: Record<string, DroneState>;

  // Survivors/thermal signatures
  survivors: Survivor[];

  // Environment obstacles (rubble blocks)
  blockedAreas: BlockedArea[];
  gridTimestamp: number;

  // Buildings
  buildings: Building[];

  // Thermal heatmap tiles — accumulated as drone scans.
  // Key = "gridX,gridY", value = highest temp_celsius seen at that cell.
  heatTiles: Record<string, number>;

  // Hover state for UI interaction
  hoveredDroneId: string | null;

  // Mission state
  missionRunning: boolean;

  // Optimized detection tracking
  detectedSurvivorIds: Set<string>;

  // Actions
  setConnectionStatus: (status: ConnectionStatus) => void;
  setDrone: (drone: DroneState) => void;
  setDrones: (drones: Record<string, DroneState>) => void;
  updateDroneTransient: (drone: DroneState) => void; // New transient-only action
  removeDrone: (droneId: string) => void;
  setSurvivors: (survivors: Survivor[]) => void;
  addSurvivor: (survivor: Survivor) => void;
  updateSurvivor: (id: string, updates: Partial<Survivor>) => void;
  setBlockedAreas: (blocked: BlockedArea[], timestamp: number) => void;
  setBuildings: (buildings: Building[]) => void;
  addHeatTiles: (tiles: Array<{ x: number; y: number; temp_celsius: number }>) => void;
  setHoveredDroneId: (droneId: string | null) => void;
  setWsUrl: (url: string) => void;
  setMissionRunning: (running: boolean) => void;
  reset: () => void;
}

// =============================================================================
// Transient/Ref State for High-Frequency Updates
// =============================================================================

/** 
 * Transient drone state stored in refs to avoid React re-renders 
 * on every WebSocket position update.
 * Use getDroneRef() and subscribeToDronePosition() for access.
 */
const dronesRef = {
  current: {} as Record<string, DroneState>,
  subscribers: new Set<(drones: Record<string, DroneState>) => void>(),
};

/**
 * Get direct reference to all drones state for high-frequency updates.
 * Does NOT trigger React re-renders.
 */
export function getDronesRef(): Record<string, DroneState> {
  return dronesRef.current;
}

/**
 * Get a specific drone by ID
 */
export function getDroneRef(droneId: string): DroneState | null {
  return dronesRef.current[droneId] || null;
}

/**
 * Subscribe to all drones position changes.
 * Callback is called on every position update without React re-renders.
 * Returns unsubscribe function.
 */
export function subscribeToDronesPosition(
  callback: (drones: Record<string, DroneState>) => void
): () => void {
  dronesRef.subscribers.add(callback);
  // Immediately call with current state
  callback(dronesRef.current);
  
  return () => {
    dronesRef.subscribers.delete(callback);
  };
}

/**
 * Subscribe to specific drone position changes.
 * Callback is called on every position update without React re-renders.
 * Returns unsubscribe function.
 */
export function subscribeToDronePosition(
  droneId: string,
  callback: (drone: DroneState | null) => void
): () => void {
  const handler = (drones: Record<string, DroneState>) => {
    callback(drones[droneId] || null);
  };
  dronesRef.subscribers.add(handler);
  // Immediately call with current state
  callback(dronesRef.current[droneId] || null);
  
  return () => {
    dronesRef.subscribers.delete(handler);
  };
}

/**
 * Update the transient drones ref and notify subscribers.
 * Internal function - called by WebSocket handler.
 */
function updateDronesRef(drone: DroneState): void {
  dronesRef.current[drone.drone_id] = drone;
  // Notify all subscribers without triggering React re-renders
  dronesRef.subscribers.forEach((callback) => callback(dronesRef.current));
}

// =============================================================================
// WebSocket Management - Single connection for send and receive
// =============================================================================

let ws: WebSocket | null = null;
let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
let reconnectDelay = 1000;
const maxReconnectDelay = 30000;

export function connectWebSocket(url?: string): void {
  const wsUrl = url || import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws/ui';

  if (ws) {
    ws.onclose = null;
    ws.onerror = null;
    ws.onmessage = null;
    ws.onopen = null;
    ws.close();
    ws = null;
  }

  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  useStore.getState().setConnectionStatus('connecting');

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('🔗 WebSocket connected:', wsUrl);
      useStore.getState().setConnectionStatus('connected');
      reconnectDelay = 1000;
    };

    ws.onclose = (event) => {
      console.log('🔌 WebSocket closed:', event.code, event.reason);
      useStore.getState().setConnectionStatus('disconnected');
      reconnectTimeout = setTimeout(() => connectWebSocket(wsUrl), reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectDelay);
    };

    ws.onerror = () => {
      useStore.getState().setConnectionStatus('error');
    };

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        handleWebSocketMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
  } catch (error) {
    console.error('Failed to create WebSocket:', error);
    useStore.getState().setConnectionStatus('error');
    reconnectTimeout = setTimeout(() => connectWebSocket(wsUrl), reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectDelay);
  }
}

// Keep legacy exports so existing callers don't break
export const connectWebSocketSend = connectWebSocket;
export const connectWebSocketReceive = connectWebSocket;

export function sendMessage(payload: object): void {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  } else {
    console.warn('WebSocket not connected for sending');
  }
}

export function disconnectWebSocket(): void {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  if (ws) {
    // Null out handlers first so onclose doesn't schedule a reconnect
    ws.onclose = null;
    ws.onerror = null;
    ws.onmessage = null;
    ws.onopen = null;
    ws.close();
    ws = null;
  }

  useStore.getState().setConnectionStatus('disconnected');
}

/**
 * Handle incoming WebSocket messages
 */
function handleWebSocketMessage(message: WebSocketMessage): void {
  switch (message.type) {
    case 'send_position': {
      const data = message as unknown as {
        type: string;
        drone_id: string;
        x: number;
        y: number;
        z: number;
        spherical: SphericalCoords;
        status?: DroneStatus;
        battery?: number;
        eta_ms: number;
        timestamp: number;
      };
      
      // Backend Z (altitude) maps to Three.js Y
      const drone: DroneState = {
        drone_id: data.drone_id,
        position: {
          x: data.x,
          y: data.z, // Z (altitude) from backend → Y in Three.js
          z: data.y, // Y from backend → Z in Three.js (ground plane)
        },
        spherical: data.spherical,
        status: data.status || 'IDLE',
        battery: typeof data.battery === 'number' ? Math.max(0, Math.min(100, data.battery)) : 100,
        eta_ms: data.eta_ms,
        timestamp: data.timestamp,
      };
      
      // Update transient ref for high-frequency 3D updates (NO React re-render)
      updateDronesRef(drone);
      
      // Update React state ONLY if status/battery or critical info changed
      // This keeps the Overlay/UI responsive without 60FPS re-renders
      const prevState = useStore.getState().drones[drone.drone_id];
      const shouldUpdateState = !prevState || 
                                prevState.status !== drone.status || 
                                Math.abs(prevState.battery - drone.battery) > 1;

      if (shouldUpdateState) {
        useStore.getState().setDrone(drone);
      }
      break;
    }
    
    case 'drone_disconnected': {
      const droneId = (message as unknown as { drone_id: string }).drone_id;
      useStore.getState().removeDrone(droneId);
      delete dronesRef.current[droneId];
      dronesRef.subscribers.forEach((cb) => cb(dronesRef.current));
      break;
    }

    case 'survivor_detected': {
      // Reconciled via global_state_update from server
      console.log('[WebSocket] Survivor message received (ignored):', message.type);
      break;
    }
    case 'survivors_update': {
      console.log('[WebSocket] Survivor message received:', message.type);
      console.log('[WebSocket] Full survivor message data:', JSON.stringify(message));
      const data = message as unknown as {
        type: string;
        drone_id: string;
        x: number;
        y: number;
        z: number;
        confidence: number;
        status?: SurvivorStatus;
        thermalSignature?: boolean;
        timestamp: number;
      };
      
      const survivor: Survivor = {
        id: `survivor_${data.timestamp}_${data.drone_id}`,
        position: {
          x: data.x,
          y: 0.3,   // fixed ground offset so survivor model sits on terrain
          z: data.z, // grid Z → Three.js Z
        },
        confidence: data.confidence,
        status: data.status || 'DETECTED',
        thermalSignature: data.thermalSignature ?? true,
        timestamp: data.timestamp,
        detected_by: data.drone_id,
      };
      
      const store = useStore.getState();
      const existing = store.survivors.find((s: Survivor) => {
        const dx = s.position.x - survivor.position.x;
        const dz = s.position.z - survivor.position.z;
        return Math.sqrt(dx * dx + dz * dz) < 1.5;
      });

      if (existing) {
        store.updateSurvivor(existing.id, { 
          confidence: Math.max(existing.confidence, survivor.confidence), 
          status: survivor.status,
          detected_by: survivor.detected_by,
          timestamp: survivor.timestamp
        });
      } else {
        store.addSurvivor(survivor);
      }
      break;
    }

    case 'global_state_update': {
      const data = message as unknown as {
        type: string;
        survivor: {
          id: string;
          x: number;
          y: number;
          z: number;
          is_detected: boolean;
          status: string;
          detected_by_drone_id: string;
          timestamp: number;
        };
      };
      
      const s = data.survivor;
      useStore.getState().updateSurvivor(s.id, {
        status: (s.status || (s.is_detected ? 'DETECTED' : 'TRAPPED')) as SurvivorStatus,
        detected_by: s.detected_by_drone_id,
        timestamp: s.timestamp,
        position: { x: s.x, y: 0.3, z: s.z }
      });
      break;
    }
    
    case 'grid_snapshot': {
      const data = message as unknown as {
        timestamp: number;
        blocked: BlockedArea[];
        command_base?: {
          x: number;
          y: number;
        };
        survivors?: Array<{
          id: string;
          x: number;
          y: number;
          z: number;
          is_detected: boolean;
          detected_by_drone_id: string;
          timestamp: number;
        }>;
      };
      
      const store = useStore.getState();
      
      // Hydrate survivors from grid snapshot if available
      if (data.survivors) {
        const survivors: Survivor[] = data.survivors.map((s: any) => ({
          id: s.id,
          position: { x: s.x, y: 0.3, z: s.z },
          status: (s.status || (s.is_detected ? 'DETECTED' : 'TRAPPED')) as SurvivorStatus,
          confidence: s.is_detected ? 1 : 0,
          thermalSignature: true,
          timestamp: s.timestamp || Date.now(),
          detected_by: s.detected_by_drone_id || '',
        }));
        store.setSurvivors(survivors);
      }
      
      // DEBUG: Log command base if present
      if (data.command_base) {
        console.log('📍 Command Base received:', data.command_base);
      }
      
      // Backend coordinates: X is X, Y is altitude, Z is ground plane
      // Convert to Three.js: X→X, Y→Z (altitude), Z→Y
      const blockedAreas: BlockedArea[] = data.blocked.map((area) => ({
        x: area.x,
        y: area.y, // This is the ground Y from backend, maps to Three.js Z
        radius: area.radius,
      }));
      
      useStore.getState().setBlockedAreas(blockedAreas, data.timestamp);
      break;
    }
    
    case 'grid_update': {
      const data = message as unknown as {
        timestamp: number;
        updates: Array<{ x: number; y: number; passable: boolean }>;
      };
      
      console.log('Grid update received:', data);
      break;
    }

    case 'scan_heatmap': {
      const data = message as unknown as {
        readings: Array<{ x: number; y: number; temp_celsius: number }>;
      };
      if (data.readings && data.readings.length > 0) {
        useStore.getState().addHeatTiles(data.readings);
      }
      break;
    }
    
        case 'init_connection': {
      const initData = message as unknown as {
        type: string;
        timestamp: number;
        buildings?: Building[];
        survivors?: Array<{
          id: string;
          x: number;
          y: number;
          z: number;
          is_detected: boolean;
          detected_by_drone_id: string;
          timestamp: number;
        }>;
      };

      // Initialize/Hydrate survivors from server
      if (initData.survivors && initData.survivors.length > 0) {
        const survivors: Survivor[] = initData.survivors.map((s: any) => ({
          id: s.id,
          position: { x: s.x, y: 0.3, z: s.z },
          status: (s.status || (s.is_detected ? 'DETECTED' : 'TRAPPED')) as SurvivorStatus,
          confidence: s.is_detected ? 1 : 0,
          thermalSignature: true,
          timestamp: s.timestamp || Date.now(),
          detected_by: s.detected_by_drone_id || '',
        }));
        useStore.getState().setSurvivors(survivors);
      }

      if (initData.buildings && initData.buildings.length > 0) {
        useStore.getState().setBuildings(initData.buildings);
      }
      break;
    }
    
    case 'aid_delivered': {
      // Drone delivered aid to (x, y) in backend coords → Three.js (x, z).
      // Find the closest survivor within 2 units and mark them as AID_SENT.
      const data = message as unknown as { x: number; y: number; drone_id: string };
      const store = useStore.getState();
      const nearest = store.survivors
        .filter(s => s.status === 'DETECTED' || s.status === 'CONFIRMED')
        .map(s => ({ s, d: Math.sqrt((s.position.x - data.x) ** 2 + (s.position.z - data.y) ** 2) }))
        .sort((a, b) => a.d - b.d)[0];
      if (nearest && nearest.d < 5) {
        store.updateSurvivor(nearest.s.id, { status: 'AID_SENT' });
      }
      break;
    }

    default:
      console.log('Unknown message type:', message.type);
  }
}

// =============================================================================
// Zustand Store
// =============================================================================

const initialState = {
  connectionStatus: 'disconnected' as ConnectionStatus,
  wsUrl: import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws/ui',
  drones: {} as Record<string, DroneState>,
  survivors: [] as Survivor[],
  blockedAreas: [] as BlockedArea[],
  gridTimestamp: 0,
  buildings: [] as Building[],
  heatTiles: {} as Record<string, number>,
  hoveredDroneId: null,
  missionRunning: false,
  detectedSurvivorIds: new Set<string>(),
};

export const useStore = create<DroneStore>((set) => ({
  ...initialState,
  
  // Actions
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  
  setDrone: (drone) => set((state) => ({
    drones: {
      ...state.drones,
      [drone.drone_id]: drone,
    },
  })),
  
  setDrones: (drones) => set({ drones }),
  
  updateDroneTransient: (drone) => {
    updateDronesRef(drone);
  },

  removeDrone: (droneId) => set((state) => {
    const newDrones = { ...state.drones };
    delete newDrones[droneId];
    return { drones: newDrones };
  }),
  
  setSurvivors: (survivors) => set((state) => {
    const STATUS_PRIORITY: Record<SurvivorStatus, number> = {
      TRAPPED: 0, DETECTED: 1, CONFIRMED: 1, AID_SENT: 2, RESCUED: 3,
    };
    // Merge incoming list with existing — preserve higher-priority statuses so
    // a grid_snapshot from the server cannot downgrade AID_SENT back to DETECTED.
    const existingMap = new Map(state.survivors.map(s => [s.id, s]));
    const merged = survivors.map(s => {
      const prev = existingMap.get(s.id);
      if (prev && s.status && STATUS_PRIORITY[s.status] < STATUS_PRIORITY[prev.status]) {
        return { ...s, status: prev.status };
      }
      return s;
    });
    const newIds = new Set(merged.filter(s => s.status !== 'TRAPPED').map(s => s.id));
    return { survivors: merged, detectedSurvivorIds: newIds };
  }),
  
  addSurvivor: (survivor) =>
    set((state) => {
      const nextIds = new Set(state.detectedSurvivorIds);
      nextIds.add(survivor.id);
      return { 
        survivors: [...state.survivors, survivor],
        detectedSurvivorIds: nextIds
      };
    }),
  
  updateSurvivor: (id, updates) =>
    set((state) => {
      const STATUS_PRIORITY: Record<SurvivorStatus, number> = {
        TRAPPED: 0, DETECTED: 1, CONFIRMED: 1, AID_SENT: 2, RESCUED: 3,
      };
      return {
        survivors: state.survivors.map((s) => {
          if (s.id !== id) return s;
          if (updates.status && STATUS_PRIORITY[updates.status] < STATUS_PRIORITY[s.status]) {
            return { ...s, ...updates, status: s.status };
          }
          return { ...s, ...updates };
        }),
      };
    }),
  
  setBlockedAreas: (blocked, timestamp) =>
    set({ blockedAreas: blocked, gridTimestamp: timestamp }),

  setBuildings: (buildings) => set({ buildings }),

  addHeatTiles: (tiles) => set((state) => {
    const next = { ...state.heatTiles };
    for (const { x, y, temp_celsius } of tiles) {
      const key = `${Math.round(x)},${Math.round(y)}`;
      if (temp_celsius > (next[key] ?? -Infinity)) {
        next[key] = temp_celsius;
      }
    }
    return { heatTiles: next };
  }),

  setHoveredDroneId: (droneId) => set({ hoveredDroneId: droneId }),

  setWsUrl: (url) => set({ wsUrl: url }),

  setMissionRunning: (running) => set({ missionRunning: running }),
  
  reset: () => {
    dronesRef.subscribers.clear();
    dronesRef.current = {};
    set(initialState);
  },
}));

// =============================================================================
// Auto-connect on store creation (optional - can be triggered manually)
// =============================================================================

// Uncomment the following line to auto-connect when the store is first used:
// connectWebSocket();

export default useStore;
