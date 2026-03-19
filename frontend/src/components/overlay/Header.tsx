import React, { useState, useEffect } from 'react';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';
import { 
  Settings, 
  Maximize, 
  Activity,
  Zap,
  Users,
  Wifi,
  Clock
} from 'lucide-react';

const StatusPill: React.FC<{ icon: React.ReactNode; label: string; value: string | number; color?: string }> = ({ icon, label, value, color = 'text-mission-neutral' }) => (
  <div className="flex items-center gap-1.5 px-2 border-r border-white/5 last:border-r-0 h-full">
    <span className={`${color} opacity-70`}>{icon}</span>
    <span className="text-[9px] uppercase tracking-tighter text-mission-neutral/50 font-mono">{label}</span>
    <span className={`text-[10px] font-bold font-mono ${color}`}>{value}</span>
  </div>
);

export const Header: React.FC = () => {
  const drones = useStore((state) => state.drones);
  const survivors = useStore((state) => state.survivors);
  const connectionStatus = useStore((state) => state.connectionStatus);
  const { toggleHighDensity } = useViewStore();
  const [time, setTime] = useState(new Date().toLocaleTimeString());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date().toLocaleTimeString()), 1000);
    return () => clearInterval(timer);
  }, []);

  const droneCount = Object.keys(drones).length;
  const foundCount = survivors.filter(s => s.status === 'RESCUED' || s.status === 'CONFIRMED').length;
  const connectionColor = connectionStatus === 'connected' ? 'text-mission-accent' : 'text-mission-critical';

  return (
    <header className="fixed top-0 left-0 w-full z-50 h-[40px] flex items-center justify-between glass-panel px-4 pointer-events-auto border-t-0 border-x-0">
      {/* Left: Mission ID & Clock */}
      <div className="flex items-center gap-4 h-full">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-mission-accent animate-pulse shadow-[0_0_8px_var(--color-mission-accent)]" />
          <h1 className="text-[11px] font-bold tracking-[0.2em] font-mono uppercase text-white/90">
            OP: RESCUE-ALPHA
          </h1>
        </div>
        <div className="h-4 w-[1px] bg-white/10" />
        <div className="flex items-center gap-2 text-mission-neutral">
          <Clock size={12} className="opacity-50" />
          <span className="text-[10px] font-mono tracking-widest">{time}</span>
        </div>
      </div>

      {/* Center: Fleet Status Pills */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center h-full bg-white/[0.02] border-x border-white/5">
        <StatusPill icon={<Zap size={12} />} label="Fleet" value={droneCount} />
        <StatusPill icon={<Users size={12} />} label="Detected" value={foundCount} color="text-mission-alert" />
        <StatusPill icon={<Wifi size={12} />} label="Link" value="12ms" color={connectionColor} />
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2 h-full">
        <button 
          onClick={toggleHighDensity}
          className="p-2 hover:bg-white/5 transition-colors text-mission-neutral hover:text-white"
          title="Toggle High Density"
        >
          <Activity size={16} />
        </button>
        <button className="p-2 hover:bg-white/5 transition-colors text-mission-neutral hover:text-white">
          <Settings size={16} />
        </button>
        <button className="p-2 hover:bg-white/5 transition-colors text-mission-neutral hover:text-white">
          <Maximize size={16} />
        </button>
        <div className="ml-2 w-7 h-7 rounded-sm bg-mission-accent/20 border border-mission-accent/40 flex items-center justify-center text-[10px] font-bold font-mono text-mission-accent">
          JD
        </div>
      </div>
    </header>
  );
};

export default Header;
