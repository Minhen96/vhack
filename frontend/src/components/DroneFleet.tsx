/**
 * DroneFleet — shows all drones with battery bar, role badge, status, altitude.
 * Clicking a row selects/deselects that drone.
 */
import type { Drone } from '@/lib/types'
import { useSimStore } from '@/store/simulation'

const ROLE_COLOUR: Record<string, string> = {
  SCOUT: 'text-accent border-accent',
  MEDIC: 'text-warning border-warning',
  RELAY: 'text-blue-400 border-blue-400',
  HEAVY: 'text-purple-400 border-purple-400',
}

const STATUS_COLOUR: Record<string, string> = {
  IDLE: 'text-muted',
  MOVING: 'text-accent',
  SCANNING: 'text-blue-400',
  DELIVERING: 'text-warning',
  RETURNING: 'text-yellow-300',
  CHARGING: 'text-green-300',
  OFFLINE: 'text-danger',
}

function batteryColour(pct: number): string {
  if (pct > 60) return 'bg-accent'
  if (pct > 30) return 'bg-warning'
  return 'bg-danger'
}

interface Props {
  selectedDroneId: string | null
  onSelect: (id: string | null) => void
}

export function DroneFleet({ selectedDroneId, onSelect }: Props) {
  const drones = useSimStore((s) => s.drones)

  return (
    <div className="flex flex-col gap-1 overflow-y-auto">
      <div className="text-xs text-muted uppercase tracking-widest mb-2 px-1">
        Drone Fleet ({drones.length})
      </div>
      {drones.length === 0 && (
        <div className="text-muted text-xs px-1">No drones deployed.</div>
      )}
      {drones.map((drone) => (
        <DroneRow
          key={drone.id}
          drone={drone}
          selected={drone.id === selectedDroneId}
          onSelect={() => onSelect(drone.id === selectedDroneId ? null : drone.id)}
        />
      ))}
    </div>
  )
}

function DroneRow({
  drone,
  selected,
  onSelect,
}: {
  drone: Drone
  selected: boolean
  onSelect: () => void
}) {
  const roleClass = ROLE_COLOUR[drone.role] ?? 'text-muted border-muted'
  const statusClass = STATUS_COLOUR[drone.status] ?? 'text-muted'
  const battery = Math.round(drone.battery)

  return (
    <button
      onClick={onSelect}
      className={`w-full text-left px-2 py-2 rounded text-xs font-mono transition-colors
        ${selected ? 'bg-surface border border-accent/50' : 'bg-surface/50 border border-transparent hover:border-border'}`}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 mb-1">
        <span
          className={`border rounded px-1 text-[10px] font-bold uppercase ${roleClass}`}
        >
          {drone.role}
        </span>
        <span className="font-bold text-white">{drone.id}</span>
        {drone.leader && (
          <span className="ml-auto text-yellow-400 text-[10px]">★ LEAD</span>
        )}
      </div>

      {/* Battery bar */}
      <div className="flex items-center gap-2 mb-1">
        <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${batteryColour(battery)}`}
            style={{ width: `${battery}%` }}
          />
        </div>
        <span className={battery < 30 ? 'text-danger' : 'text-muted'}>{battery}%</span>
      </div>

      {/* Status + position + altitude */}
      <div className="flex gap-3 text-[10px]">
        <span className={statusClass}>{drone.status}</span>
        <span className="text-muted">
          ({drone.x},{drone.y})
        </span>
        <span className="text-muted">alt={drone.altitude}m</span>
        {drone.payload && (
          <span className="text-warning ml-auto">{drone.payload}</span>
        )}
      </div>
    </button>
  )
}
