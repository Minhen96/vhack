/**
 * MetricsPanel — top-bar KPIs: phase, tick, coverage %, survivors, mesh.
 */
import { useSimStore } from '@/store/simulation'

export function MetricsPanel() {
  const mission = useSimStore((s) => s.mission)
  const connected = useSimStore((s) => s.connected)
  const drones = useSimStore((s) => s.drones)

  const meshHealth = computeMeshHealth(drones.length)

  return (
    <div className="flex items-center gap-6 px-4 py-2 bg-surface border-b border-border text-xs font-mono flex-wrap">
      {/* Connection */}
      <div className="flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full ${connected ? 'bg-accent animate-pulse' : 'bg-danger'}`}
        />
        <span className={connected ? 'text-accent' : 'text-danger'}>
          {connected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      {mission ? (
        <>
          <Metric label="PHASE" value={mission.phase} highlight />
          <Metric label="TICK" value={String(mission.tick)} />
          <Metric
            label="COVERAGE"
            value={`${mission.coverage_percent}%`}
            highlight={mission.coverage_percent > 80}
          />
          <Metric
            label="SURVIVORS"
            value={`${mission.survivors_rescued}/${mission.survivors_total}`}
            highlight={mission.survivors_rescued === mission.survivors_total && mission.survivors_total > 0}
          />
          <Metric
            label="DETECTED"
            value={String(mission.survivors_detected)}
          />
          <Metric label="MESH" value={`${meshHealth}%`} />
          {mission.paused && (
            <span className="ml-auto text-warning border border-warning/40 rounded px-2 py-0.5">
              ⏸ PAUSED
            </span>
          )}
        </>
      ) : (
        <span className="text-muted">No active mission</span>
      )}
    </div>
  )
}

function Metric({
  label,
  value,
  highlight = false,
}: {
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div className="flex gap-1.5 items-baseline">
      <span className="text-muted text-[10px] uppercase tracking-widest">{label}</span>
      <span className={highlight ? 'text-accent font-bold' : 'text-white'}>{value}</span>
    </div>
  )
}

/** Simple mesh health: ratio of online drones to total. */
function computeMeshHealth(total: number): number {
  if (total === 0) return 0
  return 100 // full mesh health when drones are present — real value comes from backend
}
