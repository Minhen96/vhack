import React, { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';
import { 
  Eye, 
  Navigation, 
  Home, 
  Battery, 
  Wind,
  Activity
} from 'lucide-react';

const AltitudeSparkline: React.FC<{ data: number[] }> = ({ data }) => {
  const points = useMemo(() => {
    if (data.length < 2) return '';
    const width = 60;
    const height = 14;
    const max = Math.max(...data, 10);
    const min = Math.min(...data, 0);
    const range = Math.max(max - min, 1);
    
    return data.map((val, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((val - min) / range) * height;
      return `${x},${y}`;
    }).join(' ');
  }, [data]);

  return (
    <div className="flex items-center gap-2">
      <svg width="60" height="14" className="overflow-visible">
        <polyline
          fill="none"
          stroke="var(--color-mission-accent)"
          strokeWidth="1.5"
          strokeLinejoin="round"
          points={points}
          className="opacity-50"
        />
      </svg>
    </div>
  );
};

const DroneCard: React.FC<{ droneId: string }> = ({ droneId }) => {
  const drone = useStore((state) => state.drones[droneId]);
  const { setFollowView, setPilotView, selectedDroneId } = useViewStore();
  const setHoveredDroneId = useStore((state) => state.setHoveredDroneId);
  const isSelected = selectedDroneId === droneId;

  if (!drone) return null;

  // Mock altitude data for sparkline
  const altitudeHistory = [5.2, 8.4, 12.1, 10.5, 9.8, 11.2, drone.position.y];

  const batteryColor = drone.battery > 50 ? 'bg-green-400' : drone.battery > 20 ? 'bg-yellow-400' : 'bg-red-500';

  return (
    <motion.div
      layout
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: -20, opacity: 0 }}
      whileHover={{ scale: 1.02 }}
      onMouseEnter={() => setHoveredDroneId(droneId)}
      onMouseLeave={() => setHoveredDroneId(null)}
      className={`
        relative w-full p-3 glass-panel cursor-pointer transition-all duration-300
        ${isSelected ? 'border-mission-accent shadow-[0_0_15px_rgba(34,211,238,0.2)] ring-1 ring-mission-accent/30 bg-mission-accent/[0.05]' : 'hover:border-white/20'}
      `}
      onClick={() => setFollowView(droneId)}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-1.5 h-1.5 rounded-full ${drone.status === 'SEARCHING' || drone.status === 'SCANNING' ? 'bg-mission-accent animate-pulse shadow-[0_0_8px_var(--color-mission-accent)]' : 'bg-mission-neutral/30'}`} />
          <span className="text-[10px] font-bold font-mono tracking-tighter text-white/90">
            DRN-{droneId.slice(-4).toUpperCase()}
          </span>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-1.5">
            <Battery size={10} className={drone.battery < 20 ? 'text-mission-critical animate-pulse' : 'text-mission-neutral/60'} />
            <span className={`text-[9px] font-mono font-bold ${drone.battery < 20 ? 'text-mission-critical' : 'text-mission-neutral'}`}>
              {drone.battery}%
            </span>
          </div>
          <div className="w-12 h-1 bg-white/5 rounded-full overflow-hidden">
            <motion.div 
              initial={{ width: 0 }}
              animate={{ width: `${drone.battery}%` }}
              className={`h-full ${batteryColor} opacity-70`}
            />
          </div>
        </div>
      </div>

      <div className="flex items-end justify-between">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5 leading-none">
            <Wind size={10} className="text-mission-neutral/40" />
            <span className="text-[11px] font-mono font-bold text-mission-accent">{drone.position.y.toFixed(1)}m</span>
            <span className="text-[8px] font-mono text-mission-neutral/40 uppercase">Alt</span>
          </div>
          <AltitudeSparkline data={altitudeHistory} />
        </div>

        <div className="flex items-center gap-1 pointer-events-auto">
          <button 
            onClick={(e) => { e.stopPropagation(); setFollowView(droneId); }}
            className={`p-1.5 rounded bg-white/5 hover:bg-mission-accent/20 hover:text-mission-accent transition-colors ${isSelected ? 'text-mission-accent bg-mission-accent/10' : 'text-mission-neutral/60'}`}
            title="Follow"
          >
            <Eye size={12} />
          </button>
          <button 
            onClick={(e) => { e.stopPropagation(); setPilotView(droneId); }}
            className="p-1.5 rounded bg-white/5 hover:bg-mission-accent/20 hover:text-mission-accent transition-colors text-mission-neutral/60"
            title="Pilot"
          >
            <Navigation size={12} />
          </button>
          <button 
            className="p-1.5 rounded bg-white/5 hover:bg-mission-accent/20 hover:text-mission-accent transition-colors text-mission-neutral/60"
            title="Return to Base"
          >
            <Home size={12} />
          </button>
        </div>
      </div>
    </motion.div>
  );
};

export const FleetSidebar: React.FC = () => {
  const drones = useStore((state) => state.drones);
  const droneIds = useMemo(() => Object.keys(drones).sort(), [drones]);

  return (
    <aside className="fixed left-6 top-[56px] bottom-24 w-60 z-40 pointer-events-none select-none flex flex-col gap-4">
      <div className="flex items-center justify-between px-2 pt-2">
        <div className="flex items-center gap-2">
          <Activity size={10} className="text-mission-accent" />
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-mission-neutral/60">Fleet Ops</span>
        </div>
        <span className="text-[9px] font-mono text-mission-accent bg-mission-accent/10 px-1.5 py-0.5 rounded uppercase font-bold border border-mission-accent/20">
          {droneIds.length} ACTIVE
        </span>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar flex flex-col gap-2 pointer-events-auto">
        <AnimatePresence mode="popLayout">
          {droneIds.map((id) => (
            <DroneCard key={id} droneId={id} />
          ))}
        </AnimatePresence>
      </div>
    </aside>
  );
};

export default FleetSidebar;
