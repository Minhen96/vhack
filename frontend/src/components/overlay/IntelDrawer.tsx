import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';
import { 
  X, 
  Battery, 
  Wifi, 
  Navigation, 
  Activity,
  AlertCircle,
  Zap,
  Package
} from 'lucide-react';

export const IntelDrawer: React.FC = () => {
  const { selectedDroneId, setFollowView } = useViewStore();
  const drone = useStore((state) => (selectedDroneId ? state.drones[selectedDroneId] : null));

  return (
    <AnimatePresence>
      {selectedDroneId && drone && (
        <motion.aside
          initial={{ x: 400, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 400, opacity: 0 }}
          className="fixed right-6 top-[56px] bottom-24 w-65 z-40 glass-panel pointer-events-auto flex flex-col overflow-hidden"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-white/[0.02]">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-mission-accent animate-pulse" />
              <span className="text-[11px] font-bold font-mono tracking-widest text-white/90 uppercase">Intel: DRN-{selectedDroneId?.slice(-4).toUpperCase()}</span>
            </div>
            <button 
              onClick={() => setFollowView(null)}
              className="p-1 hover:bg-white/10 rounded transition-colors text-white/40 hover:text-white"
            >
              <X size={14} />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto custom-scrollbar p-4 flex flex-col gap-6">
            {/* FPV Thumbnail */}
            <div className="aspect-video bg-black rounded-lg border border-white/10 relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
              <div className="absolute top-2 left-2 flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-mission-critical/20 border border-mission-critical/40">
                <div className="w-1 h-1 rounded-full bg-mission-critical animate-ping" />
                <span className="text-[8px] font-mono font-bold text-mission-critical uppercase">Live Stream</span>
              </div>
              <div className="absolute inset-0 flex items-center justify-center opacity-20 group-hover:opacity-40 transition-opacity">
                <Navigation size={48} className="text-mission-accent" />
              </div>
              <div className="absolute bottom-2 left-2 font-mono text-[8px] text-white/40">
                LAT: {drone.position.x.toFixed(4)} LNG: {drone.position.z.toFixed(4)}
              </div>
            </div>

            {/* Health Grid */}
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3 bg-white/5 rounded-xl border border-white/5 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-mission-neutral/60 uppercase">Battery</span>
                  <Battery size={12} className={drone.battery < 20 ? 'text-mission-critical' : 'text-mission-accent'} />
                </div>
                <div className="h-1.5 w-full bg-white/10 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${drone.battery}%` }}
                    className={`h-full ${drone.battery < 20 ? 'bg-mission-criticalShadow' : 'bg-mission-accent'}`}
                    style={{ backgroundColor: drone.battery < 20 ? 'var(--color-mission-critical)' : 'var(--color-mission-accent)' }}
                  />
                </div>
                <span className="text-[14px] font-mono font-bold text-white/90">{drone.battery}%</span>
              </div>

              <div className="p-3 bg-white/5 rounded-xl border border-white/5 flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-[9px] font-mono text-mission-neutral/60 uppercase">Signal</span>
                  <Wifi size={12} className="text-mission-accent" />
                </div>
                <div className="flex items-end gap-1">
                   <div className="h-3 w-1 bg-mission-accent rounded-sm" />
                   <div className="h-4 w-1 bg-mission-accent rounded-sm" />
                   <div className="h-5 w-1 bg-mission-accent rounded-sm" />
                   <div className="h-2 w-1 bg-white/20 rounded-sm" />
                </div>
                <span className="text-[14px] font-mono font-bold text-white/90">92%</span>
              </div>
            </div>

            {/* Stats List */}
            <div className="flex flex-col gap-3">
               <div className="flex items-center justify-between px-1 text-[9px] font-bold uppercase tracking-widest text-mission-neutral/40">
                  <span>System Telemetry</span>
                  <Activity size={10} />
               </div>
               <div className="space-y-1">
                  {[
                    { label: 'Altitude', value: `${drone.position.y.toFixed(1)}m`, icon: <Activity size={12} /> },
                    { label: 'Velocity', value: '4.2m/s', icon: <Zap size={12} /> },
                    { label: 'Uptime', value: '12:45', icon: <Zap size={12} /> },
                  ].map((stat, i) => (
                    <div key={i} className="flex items-center justify-between p-2 rounded bg-white/[0.02] border border-white/5">
                      <div className="flex items-center gap-2 text-mission-neutral/60">
                         {stat.icon}
                         <span className="text-[10px] uppercase font-mono">{stat.label}</span>
                      </div>
                      <span className="text-[11px] font-mono font-bold text-white/80">{stat.value}</span>
                    </div>
                  ))}
               </div>
            </div>

            {/* Tactical Logistics Card */}
            {(() => {
              const survivors = useStore.getState().survivors;
              const aidedTarget = survivors.find(s => 
                s.status === 'AID_SENT' && 
                Math.sqrt(Math.pow(s.position.x - drone.position.x, 2) + Math.pow(s.position.z - drone.position.z, 2)) < 3
              );
              
              if (!aidedTarget) return null;

              return (
                <div className="p-3 bg-mission-success/10 rounded-xl border border-mission-success/20 flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[9px] font-mono text-mission-success uppercase font-bold tracking-widest">Active Logistics</span>
                    <Package size={14} className="text-mission-success" />
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[16px] font-mono font-bold text-white/90">AID DISPATCHED</span>
                    <span className="text-[10px] font-mono text-mission-success/60">TARGET: {aidedTarget.id}</span>
                  </div>
                </div>
              );
            })()}

            {/* Alert Logs */}
            <div className="mt-auto">
               <div className="flex items-center gap-2 mb-3 px-1">
                  <AlertCircle size={12} className="text-mission-alert" />
                  <span className="text-[9px] font-bold uppercase tracking-widest text-mission-alert/60">Tactical Advisories</span>
               </div>
               <div className="space-y-2">
                  <div className="p-2 rounded bg-mission-alert/5 border border-mission-alert/10 text-[9px] font-mono text-mission-alert leading-relaxed">
                     [01:21:40] THRESHOLD REACHED: WIND SHEAR +4.2%
                  </div>
                  <div className="p-2 rounded bg-mission-accent/5 border border-mission-accent/10 text-[9px] font-mono text-mission-accent leading-relaxed">
                     [01:22:12] GRID SECTOR B-4 SCAN COMPLETE.
                  </div>
               </div>
            </div>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
};

export default IntelDrawer;
