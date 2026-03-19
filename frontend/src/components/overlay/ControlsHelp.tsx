import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Keyboard, HelpCircle, X } from 'lucide-react';

export const ControlsHelp: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="fixed bottom-[85px] left-8 z-40 pointer-events-none select-none flex flex-col items-start gap-4 origin-bottom-left">
      <AnimatePresence>
        {isExpanded && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 0.9, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            className="px-5 py-4 rounded-2xl bg-white/[0.04] backdrop-blur-md border border-white/10 shadow-2xl flex flex-col gap-4"
          >
            <div className="flex items-center justify-between w-full border-b border-white/5 pb-2 mb-1">
              <div className="flex items-center gap-2.5">
                <HelpCircle size={14} className="text-mission-accent" />
                <span className="text-[10px] font-bold font-mono uppercase tracking-[0.2em] text-white">Tactical Keymap</span>
              </div>
              <button 
                onClick={() => setIsExpanded(false)}
                className="p-1 hover:bg-white/10 rounded-md transition-colors text-white/20 hover:text-white pointer-events-auto"
              >
                <X size={12} />
              </button>
            </div>
            
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-4 group/key pointer-events-auto cursor-default">
                <kbd className="min-w-[24px] h-6 flex items-center justify-center px-1.5 rounded bg-white/10 border border-white/10 text-[10px] font-mono text-mission-accent group-hover/key:bg-mission-accent group-hover/key:text-white transition-all shadow-sm">G</kbd>
                <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 group-hover/key:text-white/50 transition-colors">Global Overview</span>
              </div>
              
              <div className="flex items-center gap-4 group/key pointer-events-auto cursor-default">
                <kbd className="min-w-[24px] h-6 flex items-center justify-center px-1.5 rounded bg-white/10 border border-white/10 text-[10px] font-mono text-mission-accent group-hover/key:bg-mission-accent group-hover/key:text-white transition-all shadow-sm">F</kbd>
                <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 group-hover/key:text-white/50 transition-colors">Follow Camera</span>
              </div>

              <div className="flex items-center gap-4 group/key pointer-events-auto cursor-default">
                <kbd className="min-w-[24px] h-6 flex items-center justify-center px-1.5 rounded bg-white/10 border border-white/10 text-[10px] font-mono text-mission-accent group-hover/key:bg-mission-accent group-hover/key:text-white transition-all shadow-sm">P</kbd>
                <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 group-hover/key:text-white/50 transition-colors">Pilot HUD</span>
              </div>

              <div className="flex items-center gap-4 group/key pointer-events-auto cursor-default">
                <kbd className="min-w-[24px] h-6 flex items-center justify-center px-1.5 rounded bg-white/10 border border-white/10 text-[10px] font-mono text-mission-accent group-hover/key:bg-mission-accent group-hover/key:text-white transition-all shadow-sm">/</kbd>
                <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 group-hover/key:text-white/50 transition-colors">Command Spotlight</span>
              </div>

              <div className="flex items-center gap-4 group/key pointer-events-auto cursor-default opacity-60">
                <kbd className="min-w-[24px] h-6 flex items-center justify-center px-1.5 rounded bg-white/10 border border-white/10 text-[10px] font-mono text-white/40 group-hover/key:bg-white/20 group-hover/key:text-white transition-all shadow-sm">Esc</kbd>
                <span className="text-[9px] font-bold uppercase tracking-widest text-white/30 group-hover/key:text-white/50 transition-colors">Close / Reset</span>
              </div>
            </div>

            <div className="mt-1 pt-3 border-t border-white/5 flex items-center gap-3 opacity-20 transition-opacity self-stretch">
              <Keyboard size={12} className="text-white" />
              <span className="text-[9px] font-mono uppercase tracking-widest text-white">Neural Interface Active</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        layout
        onClick={() => setIsExpanded(!isExpanded)}
        className={`
          pointer-events-auto flex items-center justify-center w-8 h-8 rounded-full transition-all
          ${isExpanded ? 'bg-mission-accent/20 text-mission-accent border border-mission-accent/40 shadow-[0_0_15px_rgba(34,211,238,0.2)]' : 'bg-white/5 text-white/40 hover:bg-white/10 hover:text-white border border-white/10 hover:border-white/20'}
        `}
        title={isExpanded ? "Hide Controls Help" : "Show Controls Help"}
      >
        <HelpCircle size={16} />
      </motion.button>
    </div>
  );
};

export default ControlsHelp;
