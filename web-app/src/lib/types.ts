export interface SessionSummary {
  session_id: string
  status?: string | null
  question?: string | null
  rounds?: number | null
  elapsed_seconds?: number | null
}

export interface SessionDetail {
  session_id: string
  manifest?: Record<string, unknown> | null
  state?: Record<string, unknown> | null
  events?: SessionEvent[]
  summary_md?: string | null
  summary_json?: Record<string, unknown> | null
}

export interface SessionEvent {
  type?: string
  data?: unknown
  timestamp?: string
  created_at?: string
  stage?: string
  message?: string
  [key: string]: unknown
}

export interface LaunchRequest {
  prompt: string
  prompt_style?: string
  mode?: string
  env?: Record<string, string>
  queue_only?: boolean
  session_id?: string
}

export interface LaunchResponse {
  job_id: string
  queued: boolean
  session_id?: string | null
  pid?: number | null
}
