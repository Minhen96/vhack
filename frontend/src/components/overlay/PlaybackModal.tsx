import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Pause, RotateCcw, X } from 'lucide-react';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';

// Colour palette per drone index
const DRONE_COLORS = [
  '#22d3ee', // cyan
  '#f59e0b', // amber
  '#a78bfa', // violet
  '#34d399', // emerald
  '#f87171', // red
  '#fb923c', // orange
];

const CANVAS_W = 480;
const CANVAS_H = 320;

export const PlaybackModal: React.FC = () => {
  const { isPlaybackOpen, setPlaybackOpen } = useViewStore();
  const pathHistory = useStore((s) => s.pathHistory);
  const droneTypes = useStore((s) => s.droneTypes);
  const clearPathHistory = useStore((s) => s.clearPathHistory);

  const droneIds = useMemo(() => Object.keys(pathHistory).sort(), [pathHistory]);

  // Total path length across all drones (use longest drone as timeline length)
  const maxPoints = useMemo(
    () => Math.max(1, ...droneIds.map((id) => pathHistory[id]?.length ?? 0)),
    [droneIds, pathHistory],
  );

  const [progress, setProgress] = useState(1); // 0–1, 1 = show full path
  const [playing, setPlaying] = useState(false);
  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef<number>(0);

  // Playback speed: full path in ~12s
  const PLAY_SPEED = 1 / (12 * 60); // fraction per frame @ 60fps

  const tick = useCallback(
    (ts: number) => {
      const dt = lastTsRef.current ? (ts - lastTsRef.current) / 1000 : 0;
      lastTsRef.current = ts;
      setProgress((p) => {
        const next = p + dt / 12;
        if (next >= 1) {
          setPlaying(false);
          return 1;
        }
        return next;
      });
      rafRef.current = requestAnimationFrame(tick);
    },
    [],
  );

  useEffect(() => {
    if (playing) {
      lastTsRef.current = 0;
      rafRef.current = requestAnimationFrame(tick);
    } else {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    }
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [playing, tick]);

  // Compute world bounds from all path points
  const bounds = useMemo(() => {
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const id of droneIds) {
      for (const pt of pathHistory[id] ?? []) {
        if (pt.x < minX) minX = pt.x;
        if (pt.x > maxX) maxX = pt.x;
        if (pt.z < minZ) minZ = pt.z;
        if (pt.z > maxZ) maxZ = pt.z;
      }
    }
    if (!isFinite(minX)) return { minX: 0, maxX: 30, minZ: 0, maxZ: 30 };
    const pad = 2;
    return { minX: minX - pad, maxX: maxX + pad, minZ: minZ - pad, maxZ: maxZ + pad };
  }, [droneIds, pathHistory]);

  const toCanvas = useCallback(
    (wx: number, wz: number) => {
      const margin = 28;
      const w = CANVAS_W - margin * 2;
      const h = CANVAS_H - margin * 2;
      const cx = margin + ((wx - bounds.minX) / (bounds.maxX - bounds.minX || 1)) * w;
      const cy = margin + ((wz - bounds.minZ) / (bounds.maxZ - bounds.minZ || 1)) * h;
      return { cx, cy };
    },
    [bounds],
  );

  const handleReset = () => {
    setPlaying(false);
    setProgress(0);
  };

  const handlePlayPause = () => {
    if (progress >= 1) setProgress(0);
    setPlaying((p) => !p);
  };

  if (!isPlaybackOpen) return null;

  return (
    <AnimatePresence>
      <motion.div
        key="playback-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm pointer-events-auto"
        onClick={() => setPlaybackOpen(false)}
      >
        <motion.div
          key="playback-panel"
          initial={{ scale: 0.92, opacity: 0, y: 24 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.92, opacity: 0, y: 24 }}
          transition={{ type: 'spring', stiffness: 320, damping: 28 }}
          className="glass-panel rounded-2xl p-5 w-[540px] shadow-[0_24px_80px_rgba(0,0,0,0.7)] select-none"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-[13px] font-bold font-mono tracking-widest text-white uppercase">
                Mission Playback
              </h2>
              <p className="text-[9px] font-mono text-mission-neutral/50 mt-0.5">
                {droneIds.length} drone{droneIds.length !== 1 ? 's' : ''} · {maxPoints} samples
              </p>
            </div>
            <button
              onClick={() => setPlaybackOpen(false)}
              className="p-1.5 rounded-lg hover:bg-white/10 text-white/40 hover:text-white transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          {/* SVG map */}
          <div className="rounded-xl overflow-hidden bg-black/40 border border-white/5 mb-4">
            <svg
              width={CANVAS_W}
              height={CANVAS_H}
              viewBox={`0 0 ${CANVAS_W} ${CANVAS_H}`}
              className="w-full h-auto"
            >
              {/* Grid lines */}
              {Array.from({ length: 6 }).map((_, i) => {
                const x = 28 + (i / 5) * (CANVAS_W - 56);
                const y = 28 + (i / 5) * (CANVAS_H - 56);
                return (
                  <g key={i} opacity={0.08}>
                    <line x1={x} y1={28} x2={x} y2={CANVAS_H - 28} stroke="white" strokeWidth={0.5} />
                    <line x1={28} y1={y} x2={CANVAS_W - 28} y2={y} stroke="white" strokeWidth={0.5} />
                  </g>
                );
              })}

              {/* Drone paths */}
              {droneIds.map((id, idx) => {
                const pts = pathHistory[id] ?? [];
                const color = DRONE_COLORS[idx % DRONE_COLORS.length];
                const visibleCount = Math.max(1, Math.floor(pts.length * progress));
                const visible = pts.slice(0, visibleCount);

                if (visible.length < 2) return null;

                const polyline = visible
                  .map((pt) => {
                    const { cx, cy } = toCanvas(pt.x, pt.z);
                    return `${cx},${cy}`;
                  })
                  .join(' ');

                const head = visible[visible.length - 1];
                const { cx: hx, cy: hy } = toCanvas(head.x, head.z);

                return (
                  <g key={id}>
                    {/* Trail */}
                    <polyline
                      points={polyline}
                      fill="none"
                      stroke={color}
                      strokeWidth={1.8}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                      opacity={0.6}
                    />
                    {/* Drone head dot */}
                    <circle cx={hx} cy={hy} r={5} fill={color} opacity={0.9} />
                    <circle cx={hx} cy={hy} r={9} fill={color} opacity={0.15} />
                  </g>
                );
              })}

              {/* Legend */}
              {droneIds.map((id, idx) => {
                const color = DRONE_COLORS[idx % DRONE_COLORS.length];
                const type = droneTypes[id]; // 'scanner' | 'delivery' | undefined
                const label = type ? `${id.slice(-4).toUpperCase()} [${type.slice(0, 4).toUpperCase()}]` : id.slice(-4).toUpperCase();
                return (
                  <g key={`leg-${id}`} transform={`translate(${CANVAS_W - 110}, ${14 + idx * 16})`}>
                    <rect width={8} height={3} y={4} rx={1.5} fill={color} opacity={0.8} />
                    <text x={12} y={9} fill={color} fontSize={8} fontFamily="monospace" opacity={0.9}>
                      {label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Scrubber */}
          <div className="flex items-center gap-3 mb-4">
            <input
              type="range"
              min={0}
              max={1000}
              value={Math.round(progress * 1000)}
              onChange={(e) => {
                setPlaying(false);
                setProgress(Number(e.target.value) / 1000);
              }}
              className="flex-1 accent-mission-accent h-1 cursor-pointer"
            />
            <span className="text-[9px] font-mono text-mission-neutral/50 w-8 text-right">
              {Math.round(progress * 100)}%
            </span>
          </div>

          {/* Controls */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <button
                onClick={handlePlayPause}
                className="flex items-center gap-2 px-4 py-2 rounded-full bg-mission-accent text-black font-bold text-[10px] uppercase tracking-wider hover:brightness-110 active:scale-95 transition-all"
              >
                {playing ? <Pause size={13} /> : <Play size={13} />}
                {playing ? 'Pause' : 'Play'}
              </button>
              <button
                onClick={handleReset}
                className="p-2 rounded-full hover:bg-white/10 text-white/40 hover:text-white transition-colors"
                title="Reset to start"
              >
                <RotateCcw size={14} />
              </button>
            </div>
            <button
              onClick={() => { clearPathHistory(); setProgress(0); setPlaying(false); }}
              className="text-[9px] font-mono text-mission-neutral/30 hover:text-mission-critical transition-colors"
            >
              Clear history
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default PlaybackModal;
