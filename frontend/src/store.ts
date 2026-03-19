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
  timestamp: number;
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
export type SurvivorStatus = 'DETECTED' | 'CONFIRMED' | 'RESCUED';

/** WebSocket message types */
type WebSocketMessageType = 
  | 'init_connection'
  | 'send_position'
  | 'survivor_detected'
  | 'survivors_update'
  | 'grid_snapshot'
  | 'grid_update';

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

  // Hover state for UI interaction
  hoveredDroneId: string | null;

  // Actions
  setConnectionStatus: (status: ConnectionStatus) => void;
  setDrone: (drone: DroneState) => void;
  setDrones: (drones: Record<string, DroneState>) => void;
  removeDrone: (droneId: string) => void;
  setSurvivors: (survivors: Survivor[]) => void;
  addSurvivor: (survivor: Survivor) => void;
  updateSurvivor: (id: string, updates: Partial<Survivor>) => void;
  setBlockedAreas: (blocked: BlockedArea[], timestamp: number) => void;
  setBuildings: (buildings: Building[]) => void;
  setHoveredDroneId: (droneId: string | null) => void;
  setWsUrl: (url: string) => void;
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
// WebSocket Management - Sending (UI -> Go)
// =============================================================================

let wsSend: WebSocket | null = null;
let wsReceive: WebSocket | null = null;
let reconnectTimeoutSend: ReturnType<typeof setTimeout> | null = null;
let reconnectTimeoutReceive: ReturnType<typeof setTimeout> | null = null;
let reconnectDelaySend = 1000;
let reconnectDelayReceive = 1000;
const maxReconnectDelay = 30000; // Max 30 seconds

/**
 * Connect to WebSocket server for sending messages (UI -> Go)
 */
export function connectWebSocketSend(url?: string): void {
  const wsUrl = url || import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws/ui';
  
  // Clean up existing connection
  if (wsSend) {
    wsSend.close();
    wsSend = null;
  }
  
  if (reconnectTimeoutSend) {
    clearTimeout(reconnectTimeoutSend);
    reconnectTimeoutSend = null;
  }
  
  try {
    wsSend = new WebSocket(wsUrl);
    
    wsSend.onopen = () => {
      console.log('🔗 WebSocket SEND connected:', wsUrl);
    };
    
    wsSend.onclose = (event) => {
      console.log('🔌 WebSocket SEND closed:', event.code, event.reason);
      scheduleReconnectSend(wsUrl);
    };
    
    wsSend.onerror = (error) => {
      console.error('❌ WebSocket SEND error:', error);
    };
  } catch (error) {
    console.error('Failed to create WebSocket SEND:', error);
    scheduleReconnectSend(wsUrl);
  }
}

/**
 * Connect to WebSocket server for receiving messages (Go -> UI)
 * 
 * IMPORTANT: UI clients must connect to /ws/ui to receive broadcasts from the hub.
 * The hub broadcasts drone positions to UI clients connected to /ws/ui.
 */
export function connectWebSocketReceive(url?: string): void {
  // FIX: Connect to /ws/ui instead of /ws/drone to receive broadcasts
  // The hub broadcasts to UI clients on /ws/ui, not drone clients on /ws/drone
  const wsUrl = url || import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws/ui';
  
  // Clean up existing connection
  if (wsReceive) {
    wsReceive.close();
    wsReceive = null;
  }
  
  if (reconnectTimeoutReceive) {
    clearTimeout(reconnectTimeoutReceive);
    reconnectTimeoutReceive = null;
  }
  
  // Update store connection status
  useStore.getState().setConnectionStatus('connecting');
  
  try {
    wsReceive = new WebSocket(wsUrl);
    
    wsReceive.onopen = () => {
      console.log('🔗 WebSocket RECEIVE connected:', wsUrl);
      useStore.getState().setConnectionStatus('connected');
      reconnectDelayReceive = 1000; // Reset reconnect delay on successful connection
    };
    
    wsReceive.onclose = (event) => {
      console.log('🔌 WebSocket RECEIVE closed:', event.code, event.reason);
      useStore.getState().setConnectionStatus('disconnected');
      scheduleReconnectReceive(wsUrl);
    };
    
    wsReceive.onerror = (error) => {
      console.error('❌ WebSocket RECEIVE error:', error);
      useStore.getState().setConnectionStatus('error');
    };
    
    wsReceive.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        handleWebSocketMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
  } catch (error) {
    console.error('Failed to create WebSocket RECEIVE:', error);
    useStore.getState().setConnectionStatus('error');
    scheduleReconnectReceive(wsUrl);
  }
}

/**
 * Connect to both WebSocket servers
 */
export function connectWebSocket(url?: string): void {
  connectWebSocketSend(url);
  connectWebSocketReceive(url);
}

/**
 * Send message to Go server via WebSocket
 * @param payload - Object to send as JSON
 */
export function sendMessage(payload: object): void {
  if (wsSend && wsSend.readyState === WebSocket.OPEN) {
    wsSend.send(JSON.stringify(payload));
  } else {
    console.warn('WebSocket not connected for sending');
  }
}

/**
 * Schedule reconnection for send WebSocket with exponential backoff
 */
function scheduleReconnectSend(url: string): void {
  if (reconnectTimeoutSend) {
    clearTimeout(reconnectTimeoutSend);
  }
  
  console.log(`🔄 Scheduling SEND reconnect in ${reconnectDelaySend}ms...`);
  
  reconnectTimeoutSend = setTimeout(() => {
    connectWebSocketSend(url);
  }, reconnectDelaySend);
  
  // Exponential backoff
  reconnectDelaySend = Math.min(reconnectDelaySend * 2, maxReconnectDelay);
}

/**
 * Schedule reconnection for receive WebSocket with exponential backoff
 */
function scheduleReconnectReceive(url: string): void {
  if (reconnectTimeoutReceive) {
    clearTimeout(reconnectTimeoutReceive);
  }
  
  console.log(`🔄 Scheduling RECEIVE reconnect in ${reconnectDelayReceive}ms...`);
  
  reconnectTimeoutReceive = setTimeout(() => {
    connectWebSocketReceive(url);
  }, reconnectDelayReceive);
  
  // Exponential backoff
  reconnectDelayReceive = Math.min(reconnectDelayReceive * 2, maxReconnectDelay);
}

/**
 * Disconnect WebSocket
 */
export function disconnectWebSocket(): void {
  if (reconnectTimeoutSend) {
    clearTimeout(reconnectTimeoutSend);
    reconnectTimeoutSend = null;
  }
  
  if (reconnectTimeoutReceive) {
    clearTimeout(reconnectTimeoutReceive);
    reconnectTimeoutReceive = null;
  }
  
  if (wsSend) {
    wsSend.close();
    wsSend = null;
  }
  
  if (wsReceive) {
    wsReceive.close();
    wsReceive = null;
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
      
      // Update both React state (for UI) and ref (for high-frequency access)
      useStore.getState().setDrone(drone);
      updateDronesRef(drone);
      break;
    }
    
    case 'survivor_detected':
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
      
      // Backend Z (altitude) maps to Three.js Y
      const survivor: Survivor = {
        id: `survivor_${data.timestamp}_${data.drone_id}`,
        position: {
          x: data.x,
          y: data.z, // Z (altitude) from backend → Y in Three.js
          z: data.y, // Y from backend → Z in Three.js
        },
        confidence: data.confidence,
        status: data.status || 'DETECTED',
        thermalSignature: data.thermalSignature ?? true,
        timestamp: data.timestamp,
        detected_by: data.drone_id,
      };
      
      // Check if survivor already exists (by position proximity)
      const existingIndex = useStore.getState().survivors.findIndex(
        (s) => Math.abs(s.position.x - survivor.position.x) < 1 && 
               Math.abs(s.position.z - survivor.position.z) < 1
      );
      
      if (existingIndex >= 0) {
        useStore.getState().updateSurvivor(
          useStore.getState().survivors[existingIndex].id,
          { confidence: Math.max(useStore.getState().survivors[existingIndex].confidence, survivor.confidence) }
        );
      } else {
        useStore.getState().addSurvivor(survivor);
      }
      break;
    }
    
    case 'grid_snapshot': {
      const data = message as unknown as {
        type: string;
        timestamp: number;
        blocked: BlockedArea[];
        command_base?: {
          x: number;
          y: number;
        };
      };
      
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
      // Handle incremental grid updates if needed
      console.log('Grid update received:', message);
      break;
    }
    
    case 'init_connection': {
      const initData = message as unknown as {
        type: string;
        timestamp: number;
        survivors?: Array<{
          id: string;
          x: number;
          y: number;
          z: number;
          confidence: number;
          status: string;
        }>;
        buildings?: Building[];
      };

      // Process survivors — server: {x, y=altitude(0), z=ground_z}
      // Three.js: x=x, y=ground_height(0.3), z=ground_z
      if (initData.survivors && initData.survivors.length > 0) {
        const survivors: Survivor[] = initData.survivors.map((s) => ({
          id: s.id,
          position: {
            x: s.x,
            y: 0.3,  // fixed ground level with small offset so model sits on ground
            z: s.z,  // ground plane Z coordinate
          },
          confidence: s.confidence,
          status: (s.status as SurvivorStatus) || 'DETECTED',
          thermalSignature: true,
          timestamp: initData.timestamp,
          detected_by: 'server',
        }));
        useStore.getState().setSurvivors(survivors);
      }

      // Process buildings
      if (initData.buildings && initData.buildings.length > 0) {
        useStore.getState().setBuildings(initData.buildings);
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
  hoveredDroneId: null,
};

export const useStore = create<DroneStore>((set) => ({
  // Initial state
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
  
  removeDrone: (droneId) => set((state) => {
    const newDrones = { ...state.drones };
    delete newDrones[droneId];
    return { drones: newDrones };
  }),
  
  setSurvivors: (survivors) => set({ survivors }),
  
  addSurvivor: (survivor) =>
    set((state) => ({
      survivors: [...state.survivors, survivor],
    })),
  
  updateSurvivor: (id, updates) =>
    set((state) => ({
      survivors: state.survivors.map((s) =>
        s.id === id ? { ...s, ...updates } : s
      ),
    })),
  
  setBlockedAreas: (blocked, timestamp) =>
    set({ blockedAreas: blocked, gridTimestamp: timestamp }),

  setBuildings: (buildings) => set({ buildings }),

  setHoveredDroneId: (droneId) => set({ hoveredDroneId: droneId }),
  
  setWsUrl: (url) => set({ wsUrl: url }),
  
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
