import { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  ArrowUpRight,
  AudioLines,
  Binary,
  FileText,
  LoaderCircle,
  Radio,
} from 'lucide-react'
import { fetchSession } from '../lib/api'
import { formatRelativeTime } from '../lib/format'
import { useWebSocket } from '../hooks/useWebSocket'
import { cn } from '../lib/utils'
import type { SessionDetail, SessionEvent } from '../lib/types'
import { BrainVisualizer } from './BrainVisualizer'

interface SessionViewProps {
  sessionId: string | null
  onLaunchRequested: () => void
}

export function SessionView({ sessionId, onLaunchRequested }: SessionViewProps) {
  const [detail, setDetail] = useState<SessionDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!sessionId) {
      return
    }

    fetchSession(sessionId)
      .then((payload) => {
        setDetail(payload)
      })
      .catch((loadError) => {
        setError(loadError instanceof Error ? loadError.message : 'Failed to load session')
      })
  }, [sessionId])

  const loading = Boolean(sessionId) && detail === null && error === null

  const initialEvents = detail?.events ?? []
  const { events, isConnected, connectionError } = useWebSocket(sessionId, initialEvents)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const summaryItems = useMemo(() => {
    const manifest = detail?.manifest ?? {}
    const summaryJson = detail?.summary_json ?? {}
    const state = detail?.state ?? {}

    return [
      {
        label: 'Question',
        value:
          typeof manifest.question === 'string' && manifest.question.length > 0
            ? manifest.question
            : 'No question metadata captured yet',
      },
      {
        label: 'Mode',
        value:
          typeof manifest.mode === 'string'
            ? manifest.mode
            : typeof state.mode === 'string'
              ? state.mode
              : 'Default',
      },
      {
        label: 'Winner',
        value:
          typeof summaryJson.winner === 'string'
            ? summaryJson.winner
            : typeof summaryJson.answer === 'string'
              ? summaryJson.answer
              : 'Awaiting synthesis',
      },
    ]
  }, [detail])

  if (!sessionId) {
    return (
      <div className="panel-shell flex min-h-[740px] flex-col items-center justify-center text-center">
        <div className="rounded-full border border-cyan-300/20 bg-cyan-300/10 p-4">
          <AudioLines className="h-8 w-8 text-cyan-200" />
        </div>
        <h2 className="mt-6 font-display text-3xl text-white">No session selected</h2>
        <p className="mt-3 max-w-md text-sm leading-6 text-slate-400">
          Pick a recent run from the left column or launch a fresh session to start streaming
          traces here.
        </p>
        <button className="button-primary mt-6" onClick={onLaunchRequested}>
          Launch session
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <motion.div
        className="panel-shell"
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="section-eyebrow">Session focus</p>
            <h2 className="section-title break-all">{sessionId}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              REST detail and websocket streaming are unified here so you can inspect current
              state, summary output, and live reasoning in one place.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <StatusPill
              icon={Radio}
              label={isConnected ? 'Live websocket' : 'Replay mode'}
              tone={isConnected ? 'good' : 'neutral'}
            />
            <StatusPill
              icon={Binary}
              label={connectionError ?? (loading ? 'Loading metadata' : 'REST detail loaded')}
              tone={connectionError ? 'bad' : 'neutral'}
            />
          </div>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {summaryItems.map((item) => (
            <div key={item.label} className="rounded-[24px] border border-white/10 bg-white/[0.03] p-4">
              <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{item.label}</p>
              <p className="mt-3 line-clamp-4 text-sm leading-6 text-slate-200">{item.value}</p>
            </div>
          ))}
        </div>
      </motion.div>

      <div className="grid gap-6 2xl:grid-cols-[1.15fr_0.85fr]">
        <div className="panel-shell overflow-hidden">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="section-eyebrow">Trace stream</p>
              <h3 className="section-title">Live reasoning events</h3>
            </div>
            <div className="text-xs uppercase tracking-[0.28em] text-slate-500">
              {events.length} events
            </div>
          </div>

          <div className="mt-6 h-[560px] overflow-y-auto rounded-[28px] border border-white/10 bg-slate-950/75 p-4">
            {loading && events.length === 0 ? (
              <div className="flex h-full items-center justify-center text-slate-400">
                <LoaderCircle className="mr-3 h-5 w-5 animate-spin" />
                Loading session trace
              </div>
            ) : events.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-center text-slate-500">
                <Activity className="mb-3 h-7 w-7 animate-pulse text-cyan-200/50" />
                No session events yet.
              </div>
            ) : (
              <div className="space-y-3">
                {events.map((event, index) => (
                  <LogEntry key={`${sessionId}-${index}`} event={event} />
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="panel-shell">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="section-eyebrow">System pulse</p>
                <h3 className="section-title">Neural activity</h3>
              </div>
              <StatusPill
                icon={Activity}
                label={isConnected ? 'Signal active' : 'Idle stream'}
                tone={isConnected ? 'good' : 'neutral'}
              />
            </div>
            <div className="mt-6">
              <BrainVisualizer isActive={isConnected || events.length > 0} />
            </div>
          </div>

          <div className="panel-shell">
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-amber-200" />
              <div>
                <p className="section-eyebrow">Summary</p>
                <h3 className="section-title">Rendered output</h3>
              </div>
            </div>

            <div className="mt-5 rounded-[24px] border border-white/10 bg-slate-950/70 p-4">
              {error ? (
                <p className="text-sm text-rose-100">{error}</p>
              ) : detail?.summary_md ? (
                <pre className="whitespace-pre-wrap font-mono text-xs leading-6 text-slate-300">
                  {detail.summary_md}
                </pre>
              ) : (
                <p className="text-sm leading-6 text-slate-400">
                  Summary markdown has not been emitted for this session yet.
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function LogEntry({ event }: { event: SessionEvent }) {
  const content = extractContent(event)
  const lower = content.toLowerCase()
  const tone = lower.includes('error')
    ? 'bad'
    : lower.includes('success') || lower.includes('complete') || lower.includes('pass')
      ? 'good'
      : 'neutral'

  return (
    <div
      className={cn(
        'rounded-[22px] border px-4 py-3 transition',
        tone === 'bad'
          ? 'border-rose-400/20 bg-rose-400/10'
          : tone === 'good'
            ? 'border-emerald-400/20 bg-emerald-400/10'
            : 'border-white/10 bg-white/[0.03] hover:border-cyan-300/20 hover:bg-white/[0.05]',
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">
            {event.stage || event.type || 'Event'}
          </p>
          <p className="mt-2 whitespace-pre-wrap break-words font-mono text-xs leading-6 text-slate-200">
            {content}
          </p>
        </div>
        <div className="flex flex-none items-center gap-2 text-[11px] uppercase tracking-[0.28em] text-slate-500">
          {formatRelativeTime(event.timestamp || event.created_at)}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </div>
      </div>
    </div>
  )
}

function extractContent(event: SessionEvent): string {
  if (typeof event.message === 'string' && event.message.length > 0) {
    return event.message
  }

  if (typeof event.data === 'string' && event.data.length > 0) {
    return event.data
  }

  return JSON.stringify(event, null, 2)
}

function StatusPill({
  icon: Icon,
  label,
  tone,
}: {
  icon: typeof Activity
  label: string
  tone: 'good' | 'neutral' | 'bad'
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 rounded-full border px-4 py-2 text-xs uppercase tracking-[0.24em]',
        tone === 'good'
          ? 'border-emerald-300/20 bg-emerald-300/10 text-emerald-100'
          : tone === 'bad'
            ? 'border-rose-300/20 bg-rose-300/10 text-rose-100'
            : 'border-white/10 bg-white/[0.03] text-slate-300',
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
  )
}
