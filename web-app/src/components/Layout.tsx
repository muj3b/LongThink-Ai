import type { ReactNode } from 'react'
import { BrainCircuit, Orbit, RadioTower } from 'lucide-react'
import { apiBaseUrl } from '../lib/api'

interface LayoutProps {
  children: ReactNode
  isOnline: boolean
}

export function Layout({ children, isOnline }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-primary selection:text-slate-950">
      <div className="ambient-grid" />
      <div className="ambient-orb ambient-orb-cyan" />
      <div className="ambient-orb ambient-orb-amber" />

      <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/75 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-[1440px] items-center gap-6 px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-cyan-400/30 bg-cyan-400/10 shadow-[0_0_40px_rgba(34,211,238,0.18)]">
              <BrainCircuit className="h-5 w-5 text-cyan-200" />
            </div>
            <div>
              <p className="font-display text-lg tracking-[0.2em] text-white">LONGTHINK AI</p>
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">
                Inference cockpit
              </p>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs text-slate-300 md:flex">
              <Orbit className="h-3.5 w-3.5 text-cyan-300" />
              {apiBaseUrl}
            </div>
            <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-xs font-medium uppercase tracking-[0.2em] text-slate-200">
              <RadioTower className={`h-3.5 w-3.5 ${isOnline ? 'text-emerald-300' : 'text-rose-300'}`} />
              {isOnline ? 'Backend online' : 'Backend offline'}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1440px] px-5 py-8 sm:px-8">{children}</main>
    </div>
  )
}
