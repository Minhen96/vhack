import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Send, RotateCcw, Terminal, X } from 'lucide-react';
import { useStore } from '../../store';
import { useViewStore } from '../../viewStore';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

export const CommandInput: React.FC = () => {
  const [objective, setObjective] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [missionStatus, setMissionStatus] = useState('');
  const { missionRunning, setMissionRunning } = useStore();
  const { setTerminalOpen } = useViewStore();
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // Auto-focus on mount if not running
    if (!missionRunning) {
      inputRef.current?.focus();
    }
  }, [missionRunning]);

  const handleExecute = async () => {
    if (missionRunning || !objective.trim() || isExecuting) return;

    setIsExecuting(true);
    setMissionStatus('LAUNCHING...');
    try {
      const res = await fetch(`${BACKEND_URL}/api/mission/start-background`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective: objective.trim() }),
      });
      const data = await res.json();
      
      if (data.status === 'started') {
        setMissionRunning(true);
        setMissionStatus('MISSION ACTIVE');
        // Close terminal after a short delay for feedback
        setTimeout(() => setTerminalOpen(false), 800);
      } else if (data.error) {
        setMissionStatus(`ERR: ${data.error}`);
        setMissionRunning(false);
      }
    } catch (error) {
      setMissionStatus('CONNECTION FAILED');
      setMissionRunning(false);
      console.error('Failed to start mission:', error);
    } finally {
      setIsExecuting(false);
    }
  };

  const handleReset = async () => {
    if (confirm('Are you sure you want to reset the entire fleet to base status?')) {
      try {
        const res = await fetch(`${BACKEND_URL}/api/mission/reset`, { method: 'POST' });
        if (res.ok) {
          setMissionRunning(false);
          setObjective('');
          setMissionStatus('');
          setTerminalOpen(false);
        }
      } catch (error) {
        console.error('Failed to reset mission:', error);
      }
    }
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleExecute();
    }
  };

  return (
    <motion.div 
      initial={{ scale: 0.9, opacity: 0, y: 20 }}
      animate={{ scale: 1, opacity: 1, y: 0 }}
      exit={{ scale: 0.9, opacity: 0, y: 20 }}
      className="w-[500px] glass-panel rounded-2xl shadow-[0_0_80px_rgba(34,211,238,0.15),0_20px_60px_rgba(0,0,0,0.8)] border-mission-accent/20 overflow-hidden pointer-events-auto"
    >
      <div className="flex items-center gap-3 px-4 py-3 bg-white/[0.04] border-b border-white/10">
        <Terminal size={14} className="text-mission-accent" />
        <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-white/50">Tactical Command Spotlight</span>
        <div className="ml-auto flex items-center gap-4">
           {missionRunning && (
              <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-mission-accent/10 border border-mission-accent/20">
                <span className="text-[8px] font-mono text-mission-accent uppercase font-bold tracking-widest animate-pulse">System Engaged</span>
              </div>
           )}
           <button 
            onClick={() => setTerminalOpen(false)}
            className="p-1 hover:bg-white/10 rounded-md transition-colors text-white/20 hover:text-white"
           >
            <X size={14} />
           </button>
        </div>
      </div>

      <div className="p-6 flex flex-col gap-6">
        <div className="relative group">
          <textarea
            ref={inputRef}
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={missionRunning}
            placeholder={missionRunning ? "Objective Locked - Mission in Progress" : "Type mission objective (e.g. 'Rescue survivors at sector B-4')..."}
            className={`
              w-full bg-black/40 border rounded-xl px-5 py-4 text-base font-mono transition-all resize-none min-h-[100px]
              ${missionRunning 
                ? 'border-mission-accent/20 text-white/40 cursor-not-allowed uppercase tracking-tighter' 
                : 'border-white/10 text-white placeholder:text-white/10 focus:outline-none focus:border-mission-accent/50 focus:ring-2 focus:ring-mission-accent/20'}
            `}
            rows={2}
          />
          {!missionRunning && (
            <div className="absolute bottom-3 right-4 flex items-center gap-2">
              <span className="text-[9px] font-mono text-white/20 uppercase tracking-widest bg-white/5 px-1.5 py-0.5 rounded">Enter ↵</span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4 border-t border-white/5 pt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
               <button
                  onClick={handleReset}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-mission-critical/10 border border-mission-critical/20 text-mission-critical hover:bg-mission-critical/20 transition-all text-[10px] font-bold uppercase tracking-widest"
                >
                  <RotateCcw size={14} />
                  Abort Fleet Ops
                </button>
            </div>

            <button
              onClick={handleExecute}
              disabled={!objective.trim() || isExecuting || missionRunning}
              className={`
                flex items-center gap-2 px-6 py-2.5 rounded-full transition-all active:scale-95
                ${missionRunning 
                  ? 'bg-mission-accent/20 text-mission-accent border border-mission-accent/40 shadow-[0_0_20px_rgba(34,211,238,0.2)]' 
                  : (objective.trim() && !isExecuting 
                      ? 'bg-mission-accent text-white shadow-[0_0_30px_rgba(34,211,238,0.3)] hover:brightness-110' 
                      : 'bg-white/5 text-white/20 border border-white/5 cursor-not-allowed')}
              `}
            >
              {missionRunning ? (
                <>
                  <div className="w-2 h-2 rounded-full bg-mission-accent animate-ping" />
                  <span className="text-[11px] font-bold uppercase tracking-widest">⬡ MISSION ACTIVE</span>
                </>
              ) : (
                <>
                  <Send size={16} className={isExecuting ? 'animate-pulse' : ''} />
                  <span className="text-[11px] font-bold uppercase tracking-widest">▶ LAUNCH MISSION</span>
                </>
              )}
            </button>
          </div>

          {missionStatus && (
            <div className={`
              text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-center py-2 rounded-lg bg-white/[0.02] border border-white/5
              ${missionRunning || isExecuting ? 'text-mission-accent' : 'text-mission-critical'}
            `}>
              {missionStatus}
            </div>
          )}
        </div>
      </div>

      <div className="h-0.5 w-full bg-white/5 relative overflow-hidden">
        <motion.div 
          animate={{ x: ['-100%', '100%'] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: 'linear' }}
          className="absolute inset-y-0 w-1/4 bg-gradient-to-r from-transparent via-mission-accent/50 to-transparent"
        />
      </div>
    </motion.div>
  );
};

export default CommandInput;
