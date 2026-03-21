import type {
  LaunchRequest,
  LaunchResponse,
  SessionDetail,
  SessionSummary,
} from './types'

function inferApiBaseUrl(): string {
  const override = import.meta.env.VITE_API_BASE_URL?.trim()
  if (override) {
    return override.replace(/\/$/, '')
  }

  const { protocol, hostname, port } = window.location
  if (port === '5173' || port === '4173' || hostname === 'localhost' || hostname === '127.0.0.1') {
    return `${protocol}//${hostname}:8000`
  }
  return `${protocol}//${window.location.host}`
}

export const apiBaseUrl = inferApiBaseUrl()

export function buildWebSocketUrl(sessionId: string): string {
  const url = new URL(`${apiBaseUrl}/ws/${sessionId}`)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const fallbackMessage = `${response.status} ${response.statusText}`.trim()
    let detail = fallbackMessage
    try {
      const payload = (await response.json()) as { detail?: string }
      detail = payload.detail || fallbackMessage
    } catch {
      detail = fallbackMessage
    }
    throw new Error(detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

export function fetchHealth(): Promise<{ status: string }> {
  return apiFetch('/health')
}

export function fetchPromptStyles(): Promise<string[]> {
  return apiFetch('/prompts')
}

export function fetchSessions(limit = 8): Promise<SessionSummary[]> {
  return apiFetch(`/sessions?limit=${limit}`)
}

export function fetchSession(sessionId: string): Promise<SessionDetail> {
  return apiFetch(`/sessions/${sessionId}`)
}

export function createSession(payload: LaunchRequest): Promise<LaunchResponse> {
  return apiFetch('/sessions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
