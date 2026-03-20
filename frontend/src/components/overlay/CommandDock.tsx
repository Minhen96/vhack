import React from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';
import {
  Map,
  BellOff,
  Bell,
  Navigation,
  Anchor,
  Terminal,
  CirclePlay,
  Crosshair,
  Film,
  Square,
} from 'lucide-react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export const CommandDock: React.FC = () => {
  const { missionRunning, setMissionRunning } = useStore();
  const { setTerminalOpen, triggerResetView, setPlaybackOpen } = useViewStore();
  const [muted, setMuted] = React.useState(false);
  const [stopping, setStopping] = React.useState(false);

  const handleRecall = async () => {
    if (confirm('Initiate emergency fleet recall to base?')) {
      setMissionRunning(false);
    }
  };

  const handleStopMission = async () => {
    if (stopping) return;
    setStopping(true);
    try {
      await fetch(`${BACKEND_URL}/api/mission/stop`, { method: 'POST' });
      // missionRunning will be set to false by the Overlay polling when agent stops
    } catch {
      // best-effort
    } finally {
      setStopping(false);
    }
  };

  return (
    <div className="fixed bottom-10 left-1/2 -translate-x-3/5 z-50 pointer-events-none select-none">
      <motion.div
        initial={{ y: 50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="glass-panel rounded-full px-2 py-1.5 flex items-center gap-1 shadow-[0_10px_40px_rgba(0,0,0,0.5)] pointer-events-auto"
      >
        <div className="flex items-center gap-1 px-2">
          <button
            onClick={() => setTerminalOpen(true)}
            className="p-2.5 rounded-full hover:bg-white/10 text-white/40 hover:text-mission-accent transition-all active:scale-90 flex items-center gap-2 group"
            title="Open Tactical Terminal [/]"
          >
            <Terminal size={18} />
            <span className="text-[9px] font-mono text-white/20 group-hover:text-mission-accent/50 transition-colors">[/]</span>
          </button>

          <div className="w-[1px] h-4 bg-white/5 mx-1" />

          {missionRunning ? (
            <button
              onClick={handleStopMission}
              disabled={stopping}
              className="flex items-center gap-2 px-5 py-2 rounded-full transition-all active:scale-95 font-bold bg-mission-critical/20 text-mission-critical border border-mission-critical/40 hover:bg-mission-critical/30 shadow-[0_0_20px_rgba(239,68,68,0.2)]"
              title="Stop Mission"
            >
              {stopping ? (
                <div className="w-2 h-2 rounded-full bg-mission-critical animate-ping" />
              ) : (
                <Square size={14} fill="currentColor" />
              )}
              <span className="text-[10px] uppercase tracking-wider">
                {stopping ? 'Stopping...' : 'Stop Mission'}
              </span>
            </button>
          ) : (
            <button
              onClick={() => setTerminalOpen(true)}
              className="flex items-center gap-2 px-5 py-2 rounded-full transition-all active:scale-95 font-bold bg-mission-accent text-black hover:brightness-110 shadow-[0_0_20px_rgba(34,211,238,0.35)]"
              title="Start Mission [/]"
            >
              <CirclePlay size={16} />
              <span className="text-[10px] uppercase tracking-wider">Start Mission</span>
            </button>
          )}

          <button
            onClick={handleRecall}
            className="flex items-center gap-2 px-4 py-2 rounded-full hover:bg-mission-critical/20 hover:text-mission-critical text-white/60 transition-all active:scale-95"
            title="Emergency Fleet Recall [Action-0]"
          >
            <Anchor size={16} />
            <span className="text-[10px] font-bold uppercase tracking-wider">Recall</span>
          </button>

          <div className="w-[1px] h-6 bg-white/5 mx-1" />

          <button
            onClick={triggerResetView}
            className="p-2 rounded-full hover:bg-white/10 text-white/40 hover:text-white transition-all"
            title="Reset View to Center [Home]"
          >
            <Crosshair size={18} />
          </button>

          <button
            onClick={() => setPlaybackOpen(true)}
            className="p-2 rounded-full hover:bg-white/10 text-white/40 hover:text-mission-accent transition-all"
            title="Mission Playback"
          >
            <Film size={18} />
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default CommandDock;
