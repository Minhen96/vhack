/**
 * CommandMap2D — canvas-based 30×30 grid renderer.
 *
 * Renders terrain, fire, debris, survivors, and drone positions.
 * Supports overlay modes: heatmap, risk, coverage.
 * Supports optional path and mesh overlays.
 * Click a cell to see details; click a drone to select it.
 */
import { useRef, useEffect, useCallback, useState } from 'react'
import type { Cell, Drone, Survivor, OverlayMode } from '@/lib/types'
import { useSimStore } from '@/store/simulation'

const GRID_SIZE = 30
const CELL_PX = 18 // pixels per cell
const CANVAS_SIZE = GRID_SIZE * CELL_PX

// ── Colour palette ───────────────────────────────────────────────────────

const TERRAIN_COLOUR: Record<string, string> = {
  OPEN: '#1a2035',
  DEBRIS: '#3d3522',
  RUBBLE: '#4a3f2f',
  WATER: '#1a3050',
}

function lerpColour(a: [number, number, number], b: [number, number, number], t: number): string {
  const r = Math.round(a[0] + (b[0] - a[0]) * t)
  const g = Math.round(a[1] + (b[1] - a[1]) * t)
  const bl = Math.round(a[2] + (b[2] - a[2]) * t)
  return `rgb(${r},${g},${bl})`
}

function heatColour(p: number): string {
  if (p < 0.5) return lerpColour([26, 32, 53], [180, 130, 20], p * 2)
  return lerpColour([180, 130, 20], [220, 50, 30], (p - 0.5) * 2)
}

function riskColour(cell: Cell): string {
  if (!cell.passable) return '#1f1f1f'
  if (cell.fire) return '#7f1d1d'
  if (cell.terrain === 'RUBBLE') return '#44311a'
  if (cell.debris_level >= 2) return '#3d3010'
  if (cell.debris_level === 1) return '#2d2a10'
  return '#192030'
}

function coverageColour(cell: Cell): string {
  if (!cell.searched) return '#1a2035'
  const t = cell.search_confidence
  return lerpColour([26, 32, 53], [20, 120, 60], t)
}

// ── Drone role colours ────────────────────────────────────────────────────

const ROLE_COLOUR: Record<string, string> = {
  SCOUT: '#22c55e',
  MEDIC: '#f59e0b',
  RELAY: '#60a5fa',
  HEAVY: '#a78bfa',
}

// ── Props ─────────────────────────────────────────────────────────────────

interface Props {
  overlay: OverlayMode
  showPaths: boolean
  showMesh: boolean
  onDroneSelect: (droneId: string | null) => void
  selectedDroneId: string | null
}

interface Tooltip {
  x: number
  y: number
  cell: Cell
  drone: Drone | null
  survivor: Survivor | null
}

export function CommandMap2D({
  overlay,
  showPaths,
  showMesh,
  onDroneSelect,
  selectedDroneId,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [tooltip, setTooltip] = useState<Tooltip | null>(null)

  const grid = useSimStore((s) => s.grid)
  const drones = useSimStore((s) => s.drones)
  const survivors = useSimStore((s) => s.survivors)
  const heatmap = useSimStore((s) => s.heatmap)

  // ── Draw ────────────────────────────────────────────────────────────────

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE)

    // 1. Draw grid cells
    for (let y = 0; y < GRID_SIZE; y++) {
      for (let x = 0; x < GRID_SIZE; x++) {
        const cell = grid[y]?.[x]
        if (!cell) continue

        const px = x * CELL_PX
        const py = y * CELL_PX

        // Base colour
        let colour: string
        if (overlay === 'heatmap') {
          colour = heatColour(heatmap[y]?.[x] ?? 0)
        } else if (overlay === 'risk') {
          colour = riskColour(cell)
        } else if (overlay === 'coverage') {
          colour = coverageColour(cell)
        } else {
          colour = TERRAIN_COLOUR[cell.terrain] ?? '#1a2035'
        }

        ctx.fillStyle = colour
        ctx.fillRect(px, py, CELL_PX, CELL_PX)

        // Fire overlay (always visible regardless of mode)
        if (cell.fire) {
          const intensity = Math.min(cell.fire_intensity / 3, 1)
          ctx.fillStyle = `rgba(220, 60, 20, ${0.5 + intensity * 0.4})`
          ctx.fillRect(px, py, CELL_PX, CELL_PX)
        }

        // Debris dots
        if (cell.debris_level > 0 && overlay === 'none') {
          ctx.fillStyle = 'rgba(120,100,60,0.5)'
          for (let i = 0; i < cell.debris_level; i++) {
            ctx.fillRect(px + 3 + i * 4, py + CELL_PX - 5, 2, 2)
          }
        }

        // Grid line
        ctx.strokeStyle = 'rgba(255,255,255,0.04)'
        ctx.strokeRect(px, py, CELL_PX, CELL_PX)
      }
    }

    // 2. Survivor markers
    for (const sv of survivors) {
      if (!sv.detected && !sv.rescued) continue
      const px = sv.x * CELL_PX + CELL_PX / 2
      const py = sv.y * CELL_PX + CELL_PX / 2
      ctx.beginPath()
      ctx.arc(px, py, 5, 0, Math.PI * 2)
      ctx.fillStyle = sv.rescued
        ? '#6b7280'
        : sv.condition === 'CRITICAL'
          ? '#ef4444'
          : '#f59e0b'
      ctx.fill()
      ctx.strokeStyle = '#fff'
      ctx.lineWidth = 1
      ctx.stroke()
    }

    // 3. Drone paths
    if (showPaths) {
      for (const drone of drones) {
        if (!drone.path || drone.path.length === 0) continue
        ctx.beginPath()
        ctx.moveTo(drone.x * CELL_PX + CELL_PX / 2, drone.y * CELL_PX + CELL_PX / 2)
        for (const [px, py] of drone.path) {
          ctx.lineTo(px * CELL_PX + CELL_PX / 2, py * CELL_PX + CELL_PX / 2)
        }
        ctx.strokeStyle = `${ROLE_COLOUR[drone.role] ?? '#fff'}66`
        ctx.lineWidth = 1
        ctx.setLineDash([3, 3])
        ctx.stroke()
        ctx.setLineDash([])
      }
    }

    // 4. Mesh lines
    if (showMesh) {
      const COMM_RANGE = 12 // visual only — actual range varies by role
      for (let i = 0; i < drones.length; i++) {
        for (let j = i + 1; j < drones.length; j++) {
          const a = drones[i]
          const b = drones[j]
          const dist = Math.abs(a.x - b.x) + Math.abs(a.y - b.y)
          if (dist <= COMM_RANGE) {
            ctx.beginPath()
            ctx.moveTo(a.x * CELL_PX + CELL_PX / 2, a.y * CELL_PX + CELL_PX / 2)
            ctx.lineTo(b.x * CELL_PX + CELL_PX / 2, b.y * CELL_PX + CELL_PX / 2)
            ctx.strokeStyle = 'rgba(96,165,250,0.2)'
            ctx.lineWidth = 1
            ctx.stroke()
          }
        }
      }
    }

    // 5. Drone icons
    for (const drone of drones) {
      const px = drone.x * CELL_PX + CELL_PX / 2
      const py = drone.y * CELL_PX + CELL_PX / 2
      const isSelected = drone.id === selectedDroneId
      const colour = ROLE_COLOUR[drone.role] ?? '#fff'

      // Selection ring
      if (isSelected) {
        ctx.beginPath()
        ctx.arc(px, py, 8, 0, Math.PI * 2)
        ctx.strokeStyle = colour
        ctx.lineWidth = 2
        ctx.stroke()
      }

      // Leader crown dot
      if (drone.leader) {
        ctx.beginPath()
        ctx.arc(px, py - 9, 2, 0, Math.PI * 2)
        ctx.fillStyle = '#fbbf24'
        ctx.fill()
      }

      // Drone body
      ctx.beginPath()
      ctx.arc(px, py, 5, 0, Math.PI * 2)
      ctx.fillStyle = drone.status === 'OFFLINE' ? '#6b7280' : colour
      ctx.fill()

      // Drone ID label
      ctx.fillStyle = '#fff'
      ctx.font = '7px monospace'
      ctx.textAlign = 'center'
      ctx.fillText(drone.id, px, py + 16)
    }
  }, [grid, drones, survivors, heatmap, overlay, showPaths, showMesh, selectedDroneId])

  // ── Interaction ─────────────────────────────────────────────────────────

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      const scaleX = CANVAS_SIZE / rect.width
      const scaleY = CANVAS_SIZE / rect.height
      const cx = Math.floor(((e.clientX - rect.left) * scaleX) / CELL_PX)
      const cy = Math.floor(((e.clientY - rect.top) * scaleY) / CELL_PX)

      if (cx < 0 || cx >= GRID_SIZE || cy < 0 || cy >= GRID_SIZE) {
        setTooltip(null)
        return
      }
      const cell = grid[cy]?.[cx]
      if (!cell) return

      const drone = drones.find((d) => d.x === cx && d.y === cy) ?? null
      const survivor = survivors.find((s) => s.x === cx && s.y === cy) ?? null
      setTooltip({ x: e.clientX - rect.left, y: e.clientY - rect.top, cell, drone, survivor })
    },
    [grid, drones, survivors],
  )

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const rect = canvasRef.current?.getBoundingClientRect()
      if (!rect) return
      const scaleX = CANVAS_SIZE / rect.width
      const scaleY = CANVAS_SIZE / rect.height
      const cx = Math.floor(((e.clientX - rect.left) * scaleX) / CELL_PX)
      const cy = Math.floor(((e.clientY - rect.top) * scaleY) / CELL_PX)

      const drone = drones.find((d) => d.x === cx && d.y === cy)
      onDroneSelect(drone ? drone.id : null)
    },
    [drones, onDroneSelect],
  )

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={CANVAS_SIZE}
        height={CANVAS_SIZE}
        className="w-full h-full cursor-crosshair"
        style={{ imageRendering: 'pixelated' }}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
        onClick={handleClick}
      />
      {tooltip && (
        <CellTooltip
          tooltip={tooltip}
          canvasWidth={canvasRef.current?.getBoundingClientRect().width ?? CANVAS_SIZE}
        />
      )}
    </div>
  )
}

// ── Tooltip ───────────────────────────────────────────────────────────────

function CellTooltip({
  tooltip,
  canvasWidth,
}: {
  tooltip: Tooltip
  canvasWidth: number
}) {
  const { x, y, cell, drone, survivor } = tooltip
  const flipX = x > canvasWidth * 0.6

  return (
    <div
      className="absolute z-10 pointer-events-none bg-surface border border-border rounded p-2 text-xs font-mono min-w-[140px]"
      style={{
        left: flipX ? x - 150 : x + 12,
        top: y,
      }}
    >
      <div className="text-muted mb-1">
        ({cell.x}, {cell.y}) — {cell.terrain}
      </div>
      {cell.fire && (
        <div className="text-danger">
          🔥 Fire intensity {cell.fire_intensity}
        </div>
      )}
      {cell.debris_level > 0 && (
        <div className="text-warning">Debris lvl {cell.debris_level}</div>
      )}
      {cell.searched && (
        <div className="text-accent">
          Scanned {Math.round(cell.search_confidence * 100)}%
        </div>
      )}
      {cell.probability > 0.1 && (
        <div className="text-warning">
          P(survivor) {Math.round(cell.probability * 100)}%
        </div>
      )}
      {drone && (
        <div className="mt-1 pt-1 border-t border-border text-accent">
          {drone.id} ({drone.role}) bat={Math.round(drone.battery)}%
        </div>
      )}
      {survivor && (
        <div className="mt-1 pt-1 border-t border-border text-warning">
          {survivor.id} — {survivor.condition}
          {survivor.rescued && ' ✓ RESCUED'}
        </div>
      )}
    </div>
  )
}
