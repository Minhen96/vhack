/**
 * useSimulation — manages the WebSocket connection to the backend.
 * Parses all incoming events and writes them to the Zustand store.
 * Reconnects automatically on disconnect.
 */
import { useEffect, useRef, useCallback } from 'react'
import type { WsEvent } from '@/lib/types'
import { useSimStore } from '@/store/simulation'

const WS_URL = 'ws://localhost:8000/ws/updates'
const RECONNECT_DELAY_MS = 3000

export function useSimulation(): void {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const {
    setConnected,
    initState,
    applyTickDelta,
    updateDroneAltitude,
    markSurvivorFound,
    appendAgentLog,
    resetState,
  } = useSimStore()

  const handleMessage = useCallback(
    (raw: string) => {
      let event: WsEvent
      try {
        event = JSON.parse(raw) as WsEvent
      } catch {
        return
      }

      switch (event.event) {
        case 'init': {
          const { grid, drones, survivors, mission, heatmap } = event.data
          initState(grid.cells, drones, survivors, mission, heatmap)
          break
        }
        case 'tick': {
          const { grid_delta, drones, mission } = event.data
          applyTickDelta(grid_delta, drones, mission)
          break
        }
        case 'drone_altitude': {
          updateDroneAltitude(event.data.drone_id, event.data.altitude)
          break
        }
        case 'survivor_found': {
          markSurvivorFound(event.data.x, event.data.y)
          break
        }
        case 'agent_thought': {
          appendAgentLog(event.data.phase, event.data.text)
          break
        }
        // fire_spread, aftershock, phase_change, leader_changed, aid_delivered
        // are handled indirectly via tick delta — no extra store action needed
        default:
          break
      }
    },
    [initState, applyTickDelta, updateDroneAltitude, markSurvivorFound, appendAgentLog],
  )

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      setConnected(true)
    }

    ws.onmessage = (e: MessageEvent<string>) => {
      handleMessage(e.data)
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnected(false)
      // Schedule reconnect
      reconnectTimer.current = setTimeout(() => {
        if (mountedRef.current) connect()
      }, RECONNECT_DELAY_MS)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [setConnected, handleMessage])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (reconnectTimer.current !== null) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
      resetState()
    }
  }, [connect, resetState])
}
