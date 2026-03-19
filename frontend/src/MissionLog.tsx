import { useEffect, useRef, useState } from 'react';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

interface LogEntry {
  timestamp: string;
  type: string;
  [key: string]: unknown;
}

const TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  mission_start:    { label: 'MISSION', color: '#00ffff' },
  system:           { label: 'SYS',     color: '#888888' },
  tools_discovered: { label: 'TOOLS',   color: '#4488ff' },
  tool_call:        { label: 'CALL',    color: '#ffaa00' },
  tool_result:      { label: 'RESULT',  color: '#00ff88' },
  reasoning:        { label: 'AGENT',   color: '#cc88ff' },
  mission_complete: { label: 'DONE',    color: '#00ff88' },
  error:            { label: 'ERR',     color: '#ff3366' },
};

function entryText(entry: LogEntry): string {
  switch (entry.type) {
    case 'mission_start':    return `Objective: ${(entry as {objective?: string}).objective || ''}`;
    case 'system':           return (entry as {message?: string}).message || '';
    case 'tools_discovered': return `${(entry as {count?: number}).count} tools loaded`;
    case 'tool_call': {
      const tc = entry as { tool?: string; args?: Record<string, unknown> };
      const args = tc.args ? ' ' + Object.entries(tc.args).map(([k,v]) => `${k}=${JSON.stringify(v)}`).join(' ') : '';
      return `${tc.tool}(${args.trim()})`;
    }
    case 'tool_result': {
      const tr = entry as { tool?: string; result?: string };
      const r = (tr.result || '').slice(0, 120).replace(/\n/g, ' ');
      return `${tr.tool} → ${r}`;
    }
    case 'reasoning':        return ((entry as {message?: string}).message || '').slice(0, 180);
    case 'mission_complete': return (entry as {summary?: string}).summary?.slice(0, 120) || 'Complete';
    case 'error':            return (entry as {message?: string}).message || 'Unknown error';
    default:                 return JSON.stringify(entry).slice(0, 100);
  }
}

export function MissionLog({ isRunning }: { isRunning: boolean }) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [visible, setVisible] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/mission/log`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.entries) setEntries(data.entries);
      } catch { /* ignore */ }
      if (!stopped) setTimeout(poll, 2000);
    };
    poll();
    return () => { stopped = true; };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries]);

  if (!visible) {
    return (
      <div style={{ position: 'absolute', bottom: 20, right: 20, zIndex: 1000 }}>
        <button
          onClick={() => setVisible(true)}
          style={{
            background: 'rgba(0,20,25,0.9)', border: '1px solid rgba(0,255,255,0.35)',
            borderRadius: 4, color: '#00ffff', fontSize: 10, fontFamily: 'inherit',
            letterSpacing: 2, padding: '4px 10px', cursor: 'pointer', pointerEvents: 'auto',
          }}
        >MISSION LOG ▲</button>
      </div>
    );
  }

  return (
    <div style={{
      position: 'absolute', bottom: 20, right: 20, zIndex: 1000,
      fontFamily: '"JetBrains Mono","Fira Code","Consolas",monospace',
      width: 380,
    }}>
      <div style={{
        background: 'linear-gradient(135deg,rgba(0,20,25,0.94),rgba(0,10,18,0.97))',
        border: '1px solid rgba(0,255,255,0.3)',
        borderRadius: 6,
        boxShadow: '0 0 20px rgba(0,255,255,0.1)',
        backdropFilter: 'blur(10px)',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '8px 12px', borderBottom: '1px solid rgba(0,255,255,0.15)',
        }}>
          <span style={{ color: '#00ffff', fontSize: 10, letterSpacing: 3, fontWeight: 700 }}>
            <span style={{
              display: 'inline-block', width: 7, height: 7, borderRadius: '50%', marginRight: 6,
              background: isRunning ? '#ffaa00' : '#00ff88',
              boxShadow: `0 0 6px ${isRunning ? '#ffaa00' : '#00ff88'}`,
            }} />
            MISSION LOG
          </span>
          <button
            onClick={() => setVisible(false)}
            style={{
              background: 'none', border: 'none', color: 'rgba(0,255,255,0.5)',
              fontSize: 12, cursor: 'pointer', pointerEvents: 'auto', lineHeight: 1,
            }}
          >▼</button>
        </div>

        {/* Log entries */}
        <div style={{ maxHeight: 260, overflowY: 'auto', padding: '6px 0' }}>
          {entries.length === 0 ? (
            <div style={{ color: 'rgba(0,255,255,0.3)', fontSize: 10, textAlign: 'center', padding: 16 }}>
              No mission data
            </div>
          ) : entries.map((e, i) => {
            const cfg = TYPE_CONFIG[e.type] || { label: e.type.toUpperCase(), color: '#ffffff' };
            return (
              <div key={i} style={{
                display: 'flex', gap: 8, padding: '3px 12px', alignItems: 'flex-start',
                borderBottom: '1px solid rgba(0,255,255,0.04)',
              }}>
                <span style={{
                  color: cfg.color, fontSize: 8, fontWeight: 700, letterSpacing: 1,
                  minWidth: 44, paddingTop: 1, textShadow: `0 0 6px ${cfg.color}80`,
                }}>{cfg.label}</span>
                <span style={{ color: 'rgba(200,220,220,0.8)', fontSize: 9, lineHeight: 1.5, wordBreak: 'break-word' }}>
                  {entryText(e)}
                </span>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  );
}
