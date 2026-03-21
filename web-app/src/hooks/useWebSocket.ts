import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { buildWebSocketUrl } from '../lib/api'
import type { SessionEvent } from '../lib/types'

function normalizeEvent(payload: unknown): SessionEvent {
  if (payload && typeof payload === 'object') {
    return payload as SessionEvent
  }

  return { message: String(payload) }
}

export function useWebSocket(sessionId: string | null, initialEvents: SessionEvent[] = []) {
  const [events, setEvents] = useState<SessionEvent[]>(initialEvents)
  const [isConnected, setIsConnected] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const ws = useRef<WebSocket | null>(null)

  useEffect(() => {
    setEvents(initialEvents)
  }, [initialEvents])

  const handleMessage = useEffectEvent((raw: MessageEvent<string>) => {
    const payload = JSON.parse(raw.data) as {
      type?: string
      events?: unknown[]
      data?: unknown
    }

    if (payload.type === 'init') {
      setEvents((payload.events ?? []).map(normalizeEvent))
      return
    }

    if (payload.type === 'event') {
      const nextEvent = normalizeEvent(payload.data)
      setEvents((previous) => [...previous, nextEvent])
    }
  })

  useEffect(() => {
    if (!sessionId) {
      setIsConnected(false)
      setConnectionError(null)
      return
    }

    const socket = new WebSocket(buildWebSocketUrl(sessionId))
    ws.current = socket
    setConnectionError(null)

    socket.onopen = () => {
      setIsConnected(true)
    }

    socket.onmessage = handleMessage

    socket.onerror = () => {
      setConnectionError('Live stream unavailable')
    }

    socket.onclose = () => {
      setIsConnected(false)
    }

    return () => {
      socket.close()
    }
  }, [sessionId])

  return { events, isConnected, connectionError }
}
