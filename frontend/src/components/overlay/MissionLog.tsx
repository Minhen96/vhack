import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Terminal, ChevronDown, ChevronUp, ScrollText, ArrowDown } from 'lucide-react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

interface LogEntry {
  timestamp: string;
  type: string;
  [key: string]: any;
}

const TYPE_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  mission_start:    { label: 'MISSION', color: 'text-mission-accent', bg: 'bg-mission-accent/10' },
  system:           { label: 'SYS',     color: 'text-white/40', bg: 'bg-white/5' },
  tools_discovered: { label: 'TOOLS',   color: 'text-blue-400', bg: 'bg-blue-400/10' },
  tool_call:        { label: 'CALL',    color: 'text-mission-warning', bg: 'bg-mission-warning/10' },
  tool_result:      { label: 'RESULT',  color: 'text-mission-success', bg: 'bg-mission-success/10' },
  reasoning:        { label: 'AGENT',   color: 'text-purple-400', bg: 'bg-purple-400/10' },
  mission_complete: { label: 'DONE',    color: 'text-mission-success', bg: 'bg-mission-success/20' },
  error:            { label: 'ERR',     color: 'text-mission-danger', bg: 'bg-mission-danger/10' },
};

const LogEntryRow: React.FC<{ entry: LogEntry }> = ({ entry }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const cfg = TYPE_CONFIG[entry.type] || { label: entry.type.toUpperCase(), color: 'text-white', bg: 'bg-white/5' };
  
  const summaryText = (() => {
    switch (entry.type) {
      case 'tool_call': return `Executing ${entry.tool}`;
      case 'tool_result': return `Result of ${entry.tool}`;
      case 'mission_start': return 'Mission Profile Initialized';
      case 'reasoning': return 'Strategic Analysis';
      case 'mission_complete': return 'Mission Complete';
      default: return entry.message || entry.summary || entry.type.toUpperCase();
    }
  })();

  const fullContent = (() => {
    switch (entry.type) {
      case 'mission_start':    return `Target Objective: ${entry.objective || 'Unknown'}`;
      case 'system':           return entry.message || '';
      case 'tool_call': {
        const args = entry.args ? ' ' + Object.entries(entry.args).map(([k,v]) => `${k}=${JSON.stringify(v)}`).join(' ') : '';
        return `${entry.tool}(${args.trim()})`;
      }
      case 'tool_result':      return entry.result || 'No output';
      case 'reasoning':        return entry.message || '';
      case 'mission_complete': return entry.summary || 'Mission Objective Fulfilled.';
      case 'error':            return entry.message || 'Critical System Failure';
      default:                 return JSON.stringify(entry);
    }
  })();

  const isLong = fullContent.length > 80;
  const previewText = isExpanded 
    ? summaryText 
    : (isLong ? fullContent.slice(0, 80) + '...' : fullContent);

  return (
    <motion.div 
      initial={{ x: -10, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      className={`
        flex flex-col p-2.5 rounded-xl transition-all border
        ${isExpanded 
          ? 'bg-white/[0.08] border-white/20 shadow-lg' 
          : 'bg-white/[0.02] border-white/5 hover:bg-white/[0.05]'}
      `}
    >
      <div className="flex gap-3 w-full items-start">
        <span className={`px-2 py-0.5 rounded-md text-[7px] font-bold tracking-tighter uppercase whitespace-nowrap mt-0.5 shadow-sm ${cfg.color} ${cfg.bg}`}>
          {cfg.label}
        </span>
        <div className="flex-1 min-w-0">
          <p className={`
            text-[10px] font-mono leading-relaxed transition-all break-words
            ${isExpanded ? 'text-white font-bold' : 'text-white/60'}
          `}>
            {previewText}
          </p>
          {isLong && (
            <button 
              onClick={() => setIsExpanded(!isExpanded)}
              className="mt-1 inline-flex items-center gap-1.5 text-[8px] font-bold uppercase tracking-widest text-mission-accent/40 hover:text-mission-accent transition-colors pointer-events-auto"
            >
              {isExpanded ? (
                <>Collapse Archive <ChevronUp size={10} /></>
              ) : (
                <>Expand Intelligence <ChevronDown size={10} /></>
              )}
            </button>
          )}
        </div>
      </div>
      
      <AnimatePresence>
        {isExpanded && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-2 pt-2 border-t border-white/5 w-full flex flex-col gap-2">
              {(entry.type === 'tool_result' || entry.type === 'tool_call') ? (
                <div className="relative group/code">
                  <pre className="text-[9px] font-mono p-3 rounded-lg bg-black/60 text-mission-accent/70 whitespace-pre-wrap break-all border border-white/10 max-h-[300px] overflow-y-auto custom-scrollbar shadow-inner">
                    {fullContent}
                  </pre>
                </div>
              ) : (
                <div className="p-3 rounded-lg bg-black/20 border border-white/5">
                  <p className="text-[10px] font-mono text-white/50 leading-loose italic">
                    {fullContent}
                  </p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export const MissionLog: React.FC<{ isRunning: boolean }> = ({ isRunning }) => {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [isMinimized, setIsMinimized] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const prevLengthRef = useRef(0);

  const scrollToBottom = (behavior: ScrollBehavior = 'smooth') => {
    bottomRef.current?.scrollIntoView({ behavior });
  };

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/mission/log`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.entries) {
          if (data.entries.length > prevLengthRef.current) {
            setEntries(data.entries);
            // Auto-scroll if already at bottom or just minimized
            if (!isMinimized) {
              const el = scrollRef.current;
              if (el) {
                const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 100;
                if (isAtBottom) {
                  setTimeout(() => scrollToBottom('smooth'), 50);
                } else {
                  setShowScrollButton(true);
                }
              }
            }
            prevLengthRef.current = data.entries.length;
          }
        }
      } catch { /* ignore */ }
      if (!stopped) setTimeout(poll, 1000); // Shorter poll for "streaming" feel
    };
    poll();
    return () => { stopped = true; };
  }, [isMinimized]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 40;
    setShowScrollButton(!isAtBottom);
  };

  return (
    <div className="fixed bottom-6 right-6 w-96 z-40 pointer-events-none select-none flex flex-col items-end">
      <AnimatePresence mode="wait">
        {!isMinimized ? (
          <motion.div
            key="expanded"
            initial={{ y: 20, opacity: 0, scale: 0.95 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 20, opacity: 0, scale: 0.95 }}
            className="w-full bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-2xl overflow-hidden shadow-[0_30px_60px_rgba(0,0,0,0.6)] pointer-events-auto flex flex-col relative"
          >
            {/* Header */}
            <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between bg-white/[0.04]">
              <div className="flex items-center gap-3">
                <ScrollText size={16} className="text-mission-accent" />
                <div className="flex flex-col">
                  <span className="text-[11px] font-bold uppercase tracking-[0.2em] text-white">Mission Intelligence</span>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[7px] font-mono text-white/40 uppercase">Sync Status: Optimistic</span>
                    {isRunning && (
                      <div className="flex items-center gap-1">
                        <div className="w-1 h-1 rounded-full bg-mission-warning animate-pulse" />
                        <span className="text-[7px] font-mono text-mission-warning uppercase">Streaming</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setIsMinimized(true)}
                className="p-1.5 rounded-lg hover:bg-white/10 text-white/20 hover:text-white transition-all active:scale-90"
              >
                <ChevronDown size={18} />
              </button>
            </div>

            {/* Entries Container */}
            <div 
              ref={scrollRef}
              onScroll={handleScroll}
              className="max-h-[400px] overflow-y-auto p-3 flex flex-col gap-2 custom-scrollbar scroll-smooth bg-black/20"
            >
              {entries.length === 0 ? (
                <div className="py-12 flex flex-col items-center justify-center opacity-10">
                  <Terminal size={32} />
                  <span className="text-[10px] uppercase font-mono mt-4 tracking-[0.3em]">Standby for Telemetry</span>
                </div>
              ) : (
                entries.map((e, i) => (
                  <LogEntryRow key={i} entry={e} />
                ))
              )}
              <div ref={bottomRef} className="h-1" />
            </div>

            {/* Scroll to Bottom Anchor */}
            <AnimatePresence>
              {showScrollButton && (
                <motion.button
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  onClick={() => {
                    scrollToBottom();
                  }}
                  className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1.5 bg-mission-accent text-white rounded-full shadow-lg border border-mission-accent/50 text-[9px] font-bold uppercase tracking-widest hover:brightness-110 active:scale-95 transition-all z-50 pointer-events-auto"
                >
                  <ArrowDown size={10} />
                  Back to Live
                </motion.button>
              )}
            </AnimatePresence>
          </motion.div>
        ) : (
          <motion.button
            key="collapsed"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            onClick={() => setIsMinimized(false)}
            className="flex items-center gap-4 px-6 py-3 bg-mission-bg/80 backdrop-blur-xl border border-white/10 rounded-full shadow-2xl pointer-events-auto hover:bg-white/10 transition-all group active:scale-95"
          >
            <div className="relative">
              <ScrollText size={16} className="text-mission-accent group-hover:scale-110 transition-transform" />
              {isRunning && (
                <div className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-mission-warning animate-ping" />
              )}
            </div>
            <span className="text-[11px] font-bold uppercase tracking-[0.25em] text-white/50 group-hover:text-white transition-colors">Intelligence Archive</span>
            <ChevronUp size={16} className="text-white/20 group-hover:text-white transition-colors" />
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
};

export default MissionLog;
