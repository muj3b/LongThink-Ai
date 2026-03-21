import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { LoaderCircle, Sparkles, X } from 'lucide-react'
import { createSession } from '../lib/api'
import type { LaunchRequest, LaunchResponse } from '../lib/types'

const MODES = [
  {
    value: '',
    label: 'Standard',
    description: 'Fast launch through the default orchestrator.',
  },
  {
    value: 'HYBRID',
    label: 'Hybrid',
    description: 'Blend best-of-N and tree-of-thought exploration.',
  },
  {
    value: 'TOT',
    label: 'Tree of Thought',
    description: 'Bias toward explicit planning and branch evaluation.',
  },
]

interface NewSessionModalProps {
  isOpen: boolean
  onClose: () => void
  onCreated: (response: LaunchResponse) => void
  promptStyles: string[]
  initialPrompt?: string
}

export function NewSessionModal({
  isOpen,
  onClose,
  onCreated,
  promptStyles,
  initialPrompt,
}: NewSessionModalProps) {
  const [prompt, setPrompt] = useState(initialPrompt ?? '')
  const [promptStyle, setPromptStyle] = useState('')
  const [mode, setMode] = useState('')
  const [timeBudget, setTimeBudget] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isOpen) {
      return
    }
    setPrompt(initialPrompt ?? '')
    setError(null)
  }, [initialPrompt, isOpen])

  if (!isOpen) {
    return null
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError(null)

    const payload: LaunchRequest = {
      prompt,
      prompt_style: promptStyle || undefined,
      mode: mode || undefined,
      env: timeBudget ? { TIME_BUDGET: timeBudget } : undefined,
    }

    try {
      const response = await createSession(payload)
      setPrompt('')
      setPromptStyle('')
      setMode('')
      setTimeBudget('')
      onCreated(response)
      onClose()
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Failed to launch session')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-md"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        <motion.div
          className="panel-shell w-full max-w-2xl"
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.98 }}
          transition={{ duration: 0.24, ease: 'easeOut' }}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-[11px] uppercase tracking-[0.3em] text-cyan-100">
                <Sparkles className="h-3 w-3" />
                New reasoning run
              </div>
              <h2 className="mt-4 font-display text-3xl text-white">Launch a session</h2>
              <p className="mt-2 max-w-xl text-sm text-slate-300">
                Start with a question, choose the reasoning style, and set an optional time
                budget if you want tighter control over inference depth.
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:border-white/20 hover:bg-white/10 hover:text-white"
              aria-label="Close dialog"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <label className="text-xs font-medium uppercase tracking-[0.3em] text-slate-400">
                Prompt
              </label>
              <textarea
                className="h-36 w-full rounded-[24px] border border-white/10 bg-slate-950/70 px-5 py-4 text-sm text-white outline-none transition focus:border-cyan-300/40 focus:ring-2 focus:ring-cyan-300/20"
                placeholder="Design a distributed plan for long-running inference with auditable checkpoints."
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                required
              />
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              <Field label="Prompt style">
                <select
                  className="field-input"
                  value={promptStyle}
                  onChange={(event) => setPromptStyle(event.target.value)}
                >
                  <option value="">Default</option>
                  {promptStyles.map((style) => (
                    <option key={style} value={style}>
                      {style}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Reasoning mode">
                <select
                  className="field-input"
                  value={mode}
                  onChange={(event) => setMode(event.target.value)}
                >
                  {MODES.map((option) => (
                    <option key={option.label} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field label="Time budget (s)">
                <input
                  className="field-input"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  placeholder="auto"
                  value={timeBudget}
                  onChange={(event) => setTimeBudget(event.target.value.replace(/\D/g, ''))}
                />
              </Field>
            </div>

            <div className="grid gap-3 rounded-[24px] border border-white/10 bg-white/[0.03] p-4 md:grid-cols-3">
              {MODES.map((option) => (
                <div key={option.label} className="rounded-2xl border border-white/10 bg-slate-950/60 p-4">
                  <p className="font-display text-lg text-white">{option.label}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{option.description}</p>
                </div>
              ))}
            </div>

            {error ? (
              <div className="rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
                {error}
              </div>
            ) : null}

            <div className="flex flex-col gap-3 border-t border-white/10 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-sm text-slate-400">
                Sessions launch immediately against the configured backend.
              </p>
              <div className="flex gap-3">
                <button type="button" onClick={onClose} className="button-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={loading} className="button-primary">
                  {loading ? (
                    <>
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                      Launching
                    </>
                  ) : (
                    'Start thinking'
                  )}
                </button>
              </div>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}

function Field({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <label className="block space-y-2">
      <span className="text-xs font-medium uppercase tracking-[0.3em] text-slate-400">{label}</span>
      {children}
    </label>
  )
}
