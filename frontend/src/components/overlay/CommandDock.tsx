import React from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';
import { 
  Rocket, 
  Map, 
  BellOff, 
  Bell,
  Navigation,
  Anchor,
  Terminal
} from 'lucide-react';

export const CommandDock: React.FC = () => {
  const { missionRunning, setMissionRunning } = useStore();
  const { setTerminalOpen } = useViewStore();
  const [muted, setMuted] = React.useState(false);

  const handleDeploy = async () => {
    setMissionRunning(true);
  };

  const handleRecall = async () => {
    if (confirm('Initiate emergency fleet recall to base?')) {
      setMissionRunning(false);
    }
  };

  return (
    <div className="fixed bottom-10 left-1/2 -translate-x-3/5 z-50 pointer-events-none select-none">
      <motion.div 
        initial={{ y: 50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="glass-panel rounded-full px-2 py-1.5 flex items-center gap-1 shadow-[0_10px_40px_rgba(0,0,0,0.5)] pointer-events-auto"
      >
        <div className="flex items-center gap-1 px-3 border-r border-white/5 h-8">
           <Navigation size={14} className="text-mission-accent" />
           <span className="text-[10px] font-bold font-mono tracking-widest text-white/50 uppercase">Dock</span>
        </div>

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

          <button
            onClick={handleDeploy}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-full transition-all active:scale-95
              ${missionRunning ? 'bg-mission-accent/20 text-mission-accent border border-mission-accent/20' : 'hover:bg-white/10 text-white/60'}
            `}
            title="Deploy All Drones [Action-1]"
          >
            <Rocket size={16} />
            <span className="text-[10px] font-bold uppercase tracking-wider">Deploy</span>
          </button>

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
            className="p-2 rounded-full hover:bg-white/10 text-white/40 hover:text-white transition-all"
            title="Toggle Tactical Grid [G]"
          >
            <Map size={18} />
          </button>

          <button
            onClick={() => setMuted(!muted)}
            className={`p-2 rounded-full transition-all ${muted ? 'text-mission-alert bg-mission-alert/10' : 'text-white/40 hover:bg-white/10 hover:text-white'}`}
            title={muted ? 'Unmute Alerts [M]' : 'Mute Alerts [M]'}
          >
            {muted ? <BellOff size={18} /> : <Bell size={18} />}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default CommandDock;
