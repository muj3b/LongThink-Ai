import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  ArrowRight,
  Gauge,
  PlayCircle,
  RefreshCw,
  Sparkles,
  TimerReset,
} from 'lucide-react'
import { fetchHealth, fetchPromptStyles, fetchSessions } from '../lib/api'
import { formatDuration, humanizeStatus, toSentenceCase } from '../lib/format'
import type { LaunchResponse, SessionSummary } from '../lib/types'
import { NewSessionModal } from './NewSessionModal'
import { SessionView } from './SessionView'

const QUICK_PROMPTS = [
  'Audit a distributed queue design for failure modes and observability gaps.',
  'Build a rigorous comparison between diffusion transformers and autoregressive world models.',
  'Design a safe escalation policy for long-running local reasoning jobs on consumer hardware.',
]

interface DashboardProps {
  isOnline: boolean
  onHealthChange: (nextValue: boolean) => void
}

export function Dashboard({ isOnline, onHealthChange }: DashboardProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [promptStyles, setPromptStyles] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [draftPrompt, setDraftPrompt] = useState('')

  const loadDashboard = useCallback(async ({ silent = false }: { silent?: boolean } = {}) => {
    if (silent) {
      setRefreshing(true)
    } else {
      setLoading(true)
    }

    try {
      const [health, nextSessions, styles] = await Promise.all([
        fetchHealth(),
        fetchSessions(12),
        fetchPromptStyles(),
      ])

      onHealthChange(health.status === 'ok')
      setSessions(nextSessions)
      setPromptStyles(styles)
      setSelectedSessionId((current) => current ?? nextSessions[0]?.session_id ?? null)
      setError(null)
    } catch (loadError) {
      onHealthChange(false)
      setError(loadError instanceof Error ? loadError.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [onHealthChange])

  useEffect(() => {
    void loadDashboard()

    const interval = window.setInterval(() => {
      void loadDashboard({ silent: true })
    }, 15000)

    return () => window.clearInterval(interval)
  }, [loadDashboard])

  const activeSessions = useMemo(
    () => sessions.filter((session) => !session.status || session.status === 'running').length,
    [sessions],
  )

  const totalRuntime = useMemo(
    () => sessions.reduce((sum, session) => sum + (session.elapsed_seconds ?? 0), 0),
    [sessions],
  )

  const averageRounds = useMemo(() => {
    if (sessions.length === 0) {
      return 0
    }

    const totalRounds = sessions.reduce((sum, session) => sum + (session.rounds ?? 0), 0)
    return Math.round(totalRounds / sessions.length)
  }, [sessions])

  function handleCreated(response: LaunchResponse) {
    const sessionId = response.session_id ?? null
    if (sessionId) {
      setSelectedSessionId(sessionId)
    }
    void loadDashboard({ silent: true })
  }

  return (
    <div className="space-y-8 pb-10">
      <section className="grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <motion.div
          className="panel-shell overflow-hidden"
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(245,158,11,0.18),transparent_40%)]" />
          <div className="relative space-y-6">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-[11px] uppercase tracking-[0.3em] text-cyan-100">
              <Sparkles className="h-3 w-3" />
              High-agency control plane
            </div>
            <div className="max-w-3xl">
              <h1 className="font-display text-4xl leading-none text-white md:text-6xl">
                Operate long-horizon reasoning like a live system, not a blind shell script.
              </h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300 md:text-lg">
                Monitor active runs, inspect traces, launch deeper inference modes, and keep the
                model pipeline honest while it works.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row">
              <button className="button-primary" onClick={() => setIsModalOpen(true)}>
                <PlayCircle className="h-4 w-4" />
                Launch session
              </button>
              <button
                className="button-secondary"
                onClick={() => void loadDashboard({ silent: true })}
                disabled={refreshing}
              >
                <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
                Refresh state
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  className="rounded-[24px] border border-white/10 bg-slate-950/55 p-4 text-left transition hover:-translate-y-0.5 hover:border-cyan-300/30 hover:bg-slate-950/80"
                  onClick={() => {
                    setDraftPrompt(prompt)
                    setIsModalOpen(true)
                  }}
                >
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-sm leading-6 text-slate-200">{prompt}</span>
                    <ArrowRight className="h-4 w-4 flex-none text-cyan-200" />
                  </div>
                </button>
              ))}
            </div>
          </div>
        </motion.div>

        <div className="grid gap-4">
          <StatCard
            icon={Activity}
            label="Active sessions"
            value={String(activeSessions)}
            accent={isOnline ? 'text-emerald-300' : 'text-rose-300'}
            detail={isOnline ? 'Backend healthy and polling' : 'Connection degraded or offline'}
          />
          <StatCard
            icon={TimerReset}
            label="Cumulative runtime"
            value={formatDuration(totalRuntime)}
            detail="Across recent sessions"
          />
          <StatCard
            icon={Gauge}
            label="Average rounds"
            value={String(averageRounds)}
            detail="Mean exploration depth"
          />
        </div>
      </section>

      {error ? (
        <div className="rounded-[28px] border border-rose-400/20 bg-rose-400/10 px-5 py-4 text-sm text-rose-100">
          {error}
        </div>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
        <div className="panel-shell">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="section-eyebrow">Recent sessions</p>
              <h2 className="section-title">Reasoning activity</h2>
            </div>
            <button
              className="button-secondary"
              onClick={() => void loadDashboard({ silent: true })}
              disabled={refreshing}
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              Sync
            </button>
          </div>

          <div className="mt-6 space-y-3">
            {loading ? (
              <SessionSkeleton />
            ) : sessions.length === 0 ? (
              <div className="rounded-[24px] border border-dashed border-white/10 bg-white/[0.02] px-5 py-12 text-center text-sm text-slate-400">
                No structured session runs found yet. Launch one to populate the audit trail.
              </div>
            ) : (
              sessions.map((session) => {
                const isSelected = session.session_id === selectedSessionId
                return (
                  <button
                    key={session.session_id}
                    className={`group w-full rounded-[24px] border p-4 text-left transition ${
                      isSelected
                        ? 'border-cyan-300/35 bg-cyan-300/10 shadow-[0_0_0_1px_rgba(34,211,238,0.15)]'
                        : 'border-white/10 bg-white/[0.03] hover:border-white/20 hover:bg-white/[0.05]'
                    }`}
                    onClick={() => setSelectedSessionId(session.session_id)}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={`h-2.5 w-2.5 rounded-full ${
                              !session.status || session.status === 'running'
                                ? 'bg-emerald-300 shadow-[0_0_14px_rgba(110,231,183,0.9)]'
                                : 'bg-slate-500'
                            }`}
                          />
                          <span className="text-xs uppercase tracking-[0.28em] text-slate-400">
                            {toSentenceCase(humanizeStatus(session.status))}
                          </span>
                        </div>
                        <p className="mt-3 line-clamp-2 font-display text-xl text-white">
                          {session.question || 'Untitled session'}
                        </p>
                        <p className="mt-2 truncate font-mono text-xs text-slate-500">
                          {session.session_id}
                        </p>
                      </div>
                      <ArrowRight className="mt-1 h-4 w-4 flex-none text-slate-500 transition group-hover:text-cyan-200" />
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3 text-sm text-slate-300">
                      <Metric label="Rounds" value={String(session.rounds ?? 0)} />
                      <Metric label="Runtime" value={formatDuration(session.elapsed_seconds)} />
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        <SessionView
          key={selectedSessionId ?? 'empty-session'}
          sessionId={selectedSessionId}
          onLaunchRequested={() => setIsModalOpen(true)}
        />
      </section>

      <NewSessionModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreated={handleCreated}
        promptStyles={promptStyles}
        initialPrompt={draftPrompt}
      />
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  detail,
  accent,
}: {
  icon: typeof Activity
  label: string
  value: string
  detail: string
  accent?: string
}) {
  return (
    <motion.div
      className="panel-shell"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="section-eyebrow">{label}</p>
          <p className="mt-3 font-display text-4xl text-white">{value}</p>
          <p className="mt-2 text-sm text-slate-400">{detail}</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
          <Icon className={`h-5 w-5 text-slate-200 ${accent ?? ''}`} />
        </div>
      </div>
    </motion.div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.28em] text-slate-500">{label}</p>
      <p className="mt-1 font-display text-xl text-white">{value}</p>
    </div>
  )
}

function SessionSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div
          key={index}
          className="h-28 animate-pulse rounded-[24px] border border-white/10 bg-white/[0.03]"
        />
      ))}
    </div>
  )
}
