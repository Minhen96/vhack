/**
 * App — main layout for Rescue Swarm command dashboard.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────┐
 *   │ MetricsPanel (top bar — KPIs + connection status)    │
 *   ├────────────────┬──────────────────┬──────────────────┤
 *   │ DroneFleet     │  CommandMap2D    │  MissionLog      │
 *   │ (left sidebar) │  (centre — map)  │  (right sidebar) │
 *   └────────────────┴──────────────────┴──────────────────┘
 *
 * When no mission is active, ScenarioSelector replaces the centre.
 */
import { useState } from 'react'
import { useSimulation } from '@/hooks/useSimulation'
import { useMapOverlay } from '@/hooks/useMapOverlay'
import { useSimStore } from '@/store/simulation'
import { MetricsPanel } from '@/components/MetricsPanel'
import { CommandMap2D } from '@/components/CommandMap2D'
import { DroneFleet } from '@/components/DroneFleet'
import { MissionLog } from '@/components/MissionLog'
import { ScenarioSelector } from '@/components/ScenarioSelector'

export default function App() {
  // Establish WebSocket connection — runs for lifetime of the app
  useSimulation()

  const mission = useSimStore((s) => s.mission)
  const [selectedDroneId, setSelectedDroneId] = useState<string | null>(null)
  const overlay = useMapOverlay()

  const missionActive = mission?.active ?? false

  return (
    <div className="flex flex-col h-screen bg-base text-white font-mono overflow-hidden">
      {/* Top metrics bar */}
      <MetricsPanel />

      {/* Overlay controls */}
      {missionActive && (
        <div className="flex gap-2 px-4 py-1.5 bg-surface border-b border-border text-[10px]">
          <span className="text-muted uppercase tracking-widest self-center">Overlay:</span>
          {(['none', 'heatmap', 'risk', 'coverage'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => overlay.toggleOverlay(mode)}
              className={`px-2 py-0.5 rounded border transition-colors ${
                overlay.overlay === mode
                  ? 'border-accent text-accent'
                  : 'border-border text-muted hover:border-accent/40'
              }`}
            >
              {mode === 'none' ? 'TERRAIN' : mode.toUpperCase()}
            </button>
          ))}
          <div className="w-px bg-border mx-1" />
          <button
            onClick={overlay.togglePaths}
            className={`px-2 py-0.5 rounded border transition-colors ${
              overlay.showPaths
                ? 'border-accent text-accent'
                : 'border-border text-muted hover:border-accent/40'
            }`}
          >
            PATHS
          </button>
          <button
            onClick={overlay.toggleMesh}
            className={`px-2 py-0.5 rounded border transition-colors ${
              overlay.showMesh
                ? 'border-blue-400 text-blue-400'
                : 'border-border text-muted hover:border-blue-400/40'
            }`}
          >
            MESH
          </button>
          <MissionControls />
        </div>
      )}

      {/* Main content area */}
      <div className="flex flex-1 min-h-0">
        {/* Left sidebar — drone fleet */}
        <aside className="w-52 flex-shrink-0 bg-surface border-r border-border p-2 overflow-y-auto">
          <DroneFleet
            selectedDroneId={selectedDroneId}
            onSelect={setSelectedDroneId}
          />
        </aside>

        {/* Centre — map or scenario selector */}
        <main className="flex-1 flex items-center justify-center bg-base overflow-hidden p-2">
          {missionActive ? (
            <CommandMap2D
              overlay={overlay.overlay}
              showPaths={overlay.showPaths}
              showMesh={overlay.showMesh}
              onDroneSelect={setSelectedDroneId}
              selectedDroneId={selectedDroneId}
            />
          ) : (
            <ScenarioSelector onMissionStarted={() => {}} />
          )}
        </main>

        {/* Right sidebar — ARIA log */}
        <aside className="w-72 flex-shrink-0 bg-surface border-l border-border p-2 flex flex-col">
          <MissionLog />
        </aside>
      </div>
    </div>
  )
}

// ── Mission control buttons ────────────────────────────────────────────────

const API_BASE = 'http://localhost:8000'

function MissionControls() {
  const mission = useSimStore((s) => s.mission)

  const pause = async () => {
    await fetch(`${API_BASE}/api/mission/pause`, { method: 'POST' })
  }
  const resume = async () => {
    await fetch(`${API_BASE}/api/mission/resume`, { method: 'POST' })
  }
  const reset = async () => {
    await fetch(`${API_BASE}/api/mission/reset`, { method: 'POST' })
  }

  return (
    <div className="ml-auto flex gap-2">
      {mission?.paused ? (
        <button
          onClick={resume}
          className="px-2 py-0.5 rounded border border-accent text-accent hover:bg-accent hover:text-black transition-colors"
        >
          ▶ RESUME
        </button>
      ) : (
        <button
          onClick={pause}
          className="px-2 py-0.5 rounded border border-warning text-warning hover:bg-warning hover:text-black transition-colors"
        >
          ⏸ PAUSE
        </button>
      )}
      <button
        onClick={reset}
        className="px-2 py-0.5 rounded border border-border text-muted hover:border-danger hover:text-danger transition-colors"
      >
        ↺ RESET
      </button>
    </div>
  )
}
