import React, { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Header from './components/overlay/Header';
import FleetSidebar from './components/overlay/FleetSidebar';
import IntelDrawer from './components/overlay/IntelDrawer';
import MissionLog from './components/overlay/MissionLog';
import CommandDock from './components/overlay/CommandDock';
import CommandInput from './components/overlay/CommandInput';
import ControlsHelp from './components/overlay/ControlsHelp';
import HUD from './components/overlay/HUD';
import PlaybackModal from './components/overlay/PlaybackModal';
import { useStore } from './store';
import { useViewStore } from './viewStore';

/**
 * Overlay - Glass-Bridge v2.0 (UX Polish Pass)
 * 
 * Orchestrates the Mission Control interface with:
 * - Spotlight-style Command Terminal (Shortcut: / or Enter)
 * - Dynamic Right-Panel (Intel Drawer <-> Mission Log)
 * - Cleaned footer and metadata alignment.
 */
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export const Overlay: React.FC = () => {
  const missionRunning = useStore((state) => state.missionRunning);
  const setMissionRunning = useStore((state) => state.setMissionRunning);
  const {
    highDensity,
    selectedDroneId,
    isTerminalOpen,
    setTerminalOpen,
  } = useViewStore();

  // Poll mission status while running — auto-open terminal when complete
  useEffect(() => {
    if (!missionRunning) return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/mission/log`);
        const data = await res.json();
        if (data.is_running === false) {
          setMissionRunning(false);
          setTerminalOpen(true); // prompt user for next mission
        }
      } catch {
        // ignore transient network errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [missionRunning, setMissionRunning, setTerminalOpen]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Toggle Terminal
      if ((e.key === '/' || e.key === 'Enter') && !isTerminalOpen) {
        if (document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
          e.preventDefault();
          setTerminalOpen(true);
        }
      }
      
      // Close Terminal
      if (e.key === 'Escape' && isTerminalOpen) {
        setTerminalOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isTerminalOpen, setTerminalOpen]);

  return (
    <div 
      className={`
        fixed inset-0 z-50 pointer-events-none select-none overflow-hidden
        ${highDensity ? 'scale-95 origin-center' : 'scale-100'}
        transition-transform duration-500
      `}
    >
      {/* 1. Global Header (Fixed Anchor) */}
      <Header />

      {/* 2. Operations: Fleet Sidebar (Left Anchor) */}
      <FleetSidebar />

      {/* 3. Dynamic Intel/Log Panel (Right Anchor) */}
      <div className="absolute right-6 top-[56px] bottom-24 w-80 pointer-events-none">
        <AnimatePresence mode="wait">
          {selectedDroneId ? (
            <IntelDrawer key="intel" />
          ) : (
            <MissionLog key="log" isRunning={missionRunning} />
          )}
        </AnimatePresence>
      </div>

      {/* 4. Global Action Hub: Command Dock (Bottom Anchor) */}
      <CommandDock />
      
      {/* 5. Spotlight Command Terminal (Modal Overlay) */}
      <AnimatePresence>
        {isTerminalOpen && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] flex items-center justify-center pointer-events-auto bg-black/40 backdrop-blur-[2px]"
            onClick={() => setTerminalOpen(false)}
          >
            <div onClick={(e) => e.stopPropagation()}>
              <CommandInput />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* 6. System Metadata (Bottom Left) */}
      <div className="absolute bottom-10 left-8 flex flex-col gap-0.5 opacity-40 hover:opacity-100 transition-opacity pointer-events-auto cursor-default">
        <span className="text-[10px] font-mono font-bold text-white uppercase tracking-widest">Simulation Core v2026.4</span>
        <span className="text-[8px] font-mono text-mission-accent uppercase">Advanced Operations [Dev-Build]</span>
      </div>
      
      <ControlsHelp />

      {/* 7. Dynamic Overlays: HUD (FPV / Follow Modes) */}
      <HUD />

      {/* 8. Mission Playback Modal */}
      <PlaybackModal />
    </div>
  );
};

export default Overlay;
