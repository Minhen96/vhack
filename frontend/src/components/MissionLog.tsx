/**
 * MissionLog — streams ARIA's agent_thought events in real time.
 * Auto-scrolls to the latest entry; shows phase badges.
 */
import { useEffect, useRef } from 'react'
import { useSimStore } from '@/store/simulation'
import type { AgentLogEntry } from '@/lib/types'

const PHASE_STYLE: Record<string, string> = {
  INIT: 'text-blue-400',
  OBSERVE: 'text-green-400',
  THINKING: 'text-white/80',
  EXECUTE: 'text-warning',
  RESULT: 'text-accent',
  CYCLE_END: 'text-muted',
  ERROR: 'text-danger',
  COMPLETE: 'text-accent font-bold',
}

const PHASE_BADGE: Record<string, string> = {
  INIT: 'bg-blue-900/40 text-blue-400 border-blue-600/40',
  OBSERVE: 'bg-green-900/40 text-green-400 border-green-600/40',
  THINKING: 'bg-white/5 text-white/60 border-white/10',
  EXECUTE: 'bg-yellow-900/40 text-warning border-yellow-600/40',
  RESULT: 'bg-green-900/40 text-accent border-green-600/40',
  CYCLE_END: 'bg-gray-800/40 text-muted border-gray-600/40',
  ERROR: 'bg-red-900/40 text-danger border-red-600/40',
  COMPLETE: 'bg-green-900/60 text-accent border-green-600/60',
}

export function MissionLog() {
  const log = useSimStore((s) => s.agentLog)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  return (
    <div className="flex flex-col h-full">
      <div className="text-xs text-muted uppercase tracking-widest mb-2 px-1 flex-shrink-0">
        ARIA — Mission Log
      </div>
      <div className="flex-1 overflow-y-auto space-y-1 pr-1">
        {log.length === 0 && (
          <div className="text-muted text-xs px-1 pt-2">
            Waiting for ARIA to initialise...
          </div>
        )}
        {log.map((entry) => (
          <LogEntry key={entry.id} entry={entry} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function LogEntry({ entry }: { entry: AgentLogEntry }) {
  const textClass = PHASE_STYLE[entry.phase] ?? 'text-white/70'
  const badgeClass =
    PHASE_BADGE[entry.phase] ?? 'bg-gray-800/40 text-muted border-gray-600/40'

  return (
    <div className="flex gap-2 text-xs font-mono leading-relaxed">
      <span
        className={`flex-shrink-0 border rounded px-1 text-[9px] uppercase tracking-wider ${badgeClass}`}
        style={{ alignSelf: 'flex-start', marginTop: '2px' }}
      >
        {entry.phase}
      </span>
      <span className={`break-words min-w-0 ${textClass}`}>{entry.text}</span>
    </div>
  )
}
