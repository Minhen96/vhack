/**
 * ScenarioSelector — shown when no mission is active.
 * Lets the user pick a scenario and start/reset the mission via REST.
 */
import { useState } from 'react'
import type { ScenarioKey } from '@/lib/types'

const SCENARIOS: { key: ScenarioKey; label: string; description: string }[] = [
  {
    key: 'EARTHQUAKE_ALPHA',
    label: 'Earthquake Alpha',
    description: 'Urban collapse — 5 survivors, fire spread, debris fields.',
  },
  {
    key: 'TYPHOON_BETA',
    label: 'Typhoon Beta',
    description: 'Flood zone — survivors on elevated terrain, water hazards.',
  },
  {
    key: 'STRESS_TEST',
    label: 'Stress Test',
    description: 'Maximum density — many survivors, rapid fire, high debris.',
  },
]

const API_BASE = 'http://localhost:8000'

interface Props {
  onMissionStarted: () => void
}

export function ScenarioSelector({ onMissionStarted }: Props) {
  const [selected, setSelected] = useState<ScenarioKey>('EARTHQUAKE_ALPHA')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleStart = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/mission/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: selected }),
      })
      const json = (await res.json()) as { success: boolean; detail?: string }
      if (!res.ok || !json.success) {
        setError(json.detail ?? 'Failed to start mission.')
        return
      }
      onMissionStarted()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Network error.')
    } finally {
      setLoading(false)
    }
  }

  const handleReset = async () => {
    setLoading(true)
    setError(null)
    try {
      await fetch(`${API_BASE}/api/mission/reset`, { method: 'POST' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
      <div className="text-center">
        <div className="text-accent text-lg font-bold tracking-widest mb-1">
          RESCUE SWARM
        </div>
        <div className="text-muted text-xs">Select scenario to deploy ARIA</div>
      </div>

      <div className="flex flex-col gap-2 w-full max-w-sm">
        {SCENARIOS.map((s) => (
          <button
            key={s.key}
            onClick={() => setSelected(s.key)}
            className={`text-left px-4 py-3 rounded border font-mono text-sm transition-colors
              ${
                selected === s.key
                  ? 'border-accent bg-accent/10 text-white'
                  : 'border-border bg-surface/50 text-muted hover:border-accent/40 hover:text-white'
              }`}
          >
            <div className="font-bold text-xs uppercase tracking-wider mb-0.5">
              {s.label}
            </div>
            <div className="text-[11px] text-muted">{s.description}</div>
          </button>
        ))}
      </div>

      {error && (
        <div className="text-danger text-xs border border-danger/30 rounded px-3 py-2 max-w-sm w-full">
          {error}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleReset}
          disabled={loading}
          className="px-4 py-2 text-xs font-mono border border-border text-muted rounded hover:border-accent/40 hover:text-white disabled:opacity-50 transition-colors"
        >
          RESET
        </button>
        <button
          onClick={handleStart}
          disabled={loading}
          className="px-6 py-2 text-xs font-mono font-bold border border-accent text-accent rounded hover:bg-accent hover:text-black disabled:opacity-50 transition-colors"
        >
          {loading ? 'DEPLOYING...' : 'DEPLOY ARIA'}
        </button>
      </div>
    </div>
  )
}
