import React from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';

const Crosshair: React.FC = () => (
  <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-40">
    <div className="relative w-32 h-32">
      {/* Reticle Lines */}
      <div className="absolute top-1/2 left-0 w-8 h-[1px] bg-mission-accent -translate-y-1/2" />
      <div className="absolute top-1/2 right-0 w-8 h-[1px] bg-mission-accent -translate-y-1/2" />
      <div className="absolute top-0 left-1/2 w-[1px] h-8 bg-mission-accent -translate-x-1/2" />
      <div className="absolute bottom-0 left-1/2 w-[1px] h-8 bg-mission-accent -translate-x-1/2" />

      {/* Center Point */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-1 h-1 bg-white rounded-full" />
      
      {/* Outer Brackets */}
      <div className="absolute top-0 left-0 w-4 h-4 border-t-2 border-l-2 border-mission-accent rounded-tl-sm" />
      <div className="absolute top-0 right-0 w-4 h-4 border-t-2 border-r-2 border-mission-accent rounded-tr-sm" />
      <div className="absolute bottom-0 left-0 w-4 h-4 border-b-2 border-l-2 border-mission-accent rounded-bl-sm" />
      <div className="absolute bottom-0 right-0 w-4 h-4 border-b-2 border-r-2 border-mission-accent rounded-br-sm" />
    </div>
  </div>
);

const Tape: React.FC<{ side: 'left' | 'right'; value: number; unit: string; label: string }> = ({ side, value, unit, label }) => {
  const isLeft = side === 'left';
  
  return (
    <div className={`absolute top-1/2 -translate-y-1/2 ${isLeft ? 'left-1/4' : 'right-1/4'} pointer-events-none h-64 w-24 flex flex-col items-center select-none`}>
      <div className="text-[10px] font-mono text-white/30 uppercase tracking-[0.2em] mb-4">{label}</div>
      <div className="relative flex-1 w-full border-x border-mission-accent/20 bg-mission-accent/5 overflow-hidden flex flex-col items-center">
         {/* Tick Marks Simulation */}
         <div className="flex flex-col gap-8 py-32 opacity-20">
            {[...Array(10)].map((_, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <div className="w-4 h-[1px] bg-white" />
                <span className="text-[8px] font-mono text-white/50">{(value + (5-i)*10).toFixed(0)}</span>
              </div>
            ))}
         </div>
         {/* Value Indicator */}
         <div className="absolute top-1/2 -translate-y-1/2 w-full flex items-center justify-center pointer-events-none">
            <div className={`
              absolute ${isLeft ? '-left-2' : '-right-2'} 
              w-0 h-0 
              border-y-[6px] border-y-transparent 
              ${isLeft ? 'border-l-[8px] border-l-mission-accent' : 'border-r-[8px] border-r-mission-accent'}
            `} />
            <div className="bg-mission-accent px-2 py-1 rounded text-xs font-mono font-bold text-white shadow-[0_0_15px_rgba(59,130,246,0.5)]">
               {value.toFixed(1)}<span className="text-[8px] ml-0.5 opacity-70">{unit}</span>
            </div>
         </div>
      </div>
    </div>
  );
};

const Compass: React.FC = () => (
  <div className="absolute top-24 left-1/2 -translate-x-1/2 pointer-events-none w-1/3 flex flex-col items-center">
    <div className="w-full h-8 overflow-hidden border-b border-mission-accent/30 relative">
      <div className="h-full flex items-center justify-center opacity-40 font-mono text-[10px] tracking-[0.5em] text-white">
        W · · · · N · · · · E · · · · S · · · · W
      </div>
      <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-x-[5px] border-x-transparent border-b-[5px] border-b-mission-accent" />
    </div>
    <div className="mt-2 font-mono text-lg font-bold text-mission-accent flex items-baseline gap-1">
      <span className="opacity-50 text-[10px]">HDG</span> 042°
    </div>
  </div>
);

export const HUD: React.FC = () => {
  const { viewMode, selectedDroneId } = useViewStore();
  const drones = useStore((state) => state.drones);
  const selectedDrone = selectedDroneId ? drones[selectedDroneId] : null;

  if (viewMode === 'GLOBAL' || !selectedDrone) return null;

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 pointer-events-none z-30 overflow-hidden"
    >
      {/* Tactical Elements - Only in Pilot Mode */}
      {viewMode === 'PILOT' && <Crosshair />}
      
      {/* Telemetry Tapes */}
      <Tape side="left" value={selectedDrone.position.y} unit="M" label="Altitude" />
      <Tape side="right" value={45.2} unit="KMH" label="Speed" />
      <Compass />

      {/* Mode Indicator */}
      <div className="absolute top-36 left-1/2 -translate-x-1/2 flex items-center gap-2">
        <div className={`px-2 py-0.5 rounded border text-[9px] font-bold uppercase tracking-[0.3em] font-mono shadow-[0_0_10px_rgba(59,130,246,0.3)]
          ${viewMode === 'PILOT' ? 'bg-mission-danger/20 border-mission-danger/40 text-mission-danger' : 'bg-mission-accent/20 border-mission-accent/40 text-mission-accent'}
        `}>
          {viewMode} OPS MODE
        </div>
      </div>

      {/* Warning Flash Overlay (Subtle) */}
      {selectedDrone.battery < 20 && (
        <div className="absolute inset-0 bg-red-500/5 animate-pulse-slow pointer-events-none ring-[20px] ring-red-500/10 ring-inset" />
      )}
      
      {/* Vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,transparent_40%,rgba(0,0,0,0.4)_100%)]" />
    </motion.div>
  );
};

export default HUD;
