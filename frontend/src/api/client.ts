import type {
  ChatRequest,
  ChatResponse,
  DatabasePingResponse,
  TablesResponse,
} from '../types/api'

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const apiKey = import.meta.env.VITE_ASKME_API_KEY ?? ''

export class ApiClientError extends Error {
  code: string
  status: number

  constructor(message: string, code = 'REQUEST_FAILED', status = 0) {
    super(message)
    this.name = 'ApiClientError'
    this.code = code
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  headers.set('Content-Type', 'application/json')
  if (apiKey) headers.set('X-API-Key', apiKey)

  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers })
  } catch {
    throw new ApiClientError(
      'Cannot reach the backend. Confirm that FastAPI is running on port 8000.',
      'NETWORK_ERROR',
    )
  }

  const body = await response.json().catch(() => null) as
    | { detail?: { code?: string; message?: string } | string }
    | null

  if (!response.ok) {
    const detail = body?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail?.message ?? `Request failed with HTTP ${response.status}.`
    const code = typeof detail === 'object' ? detail?.code ?? 'REQUEST_FAILED' : 'REQUEST_FAILED'
    throw new ApiClientError(message, code, response.status)
  }

  return body as T
}

export function sendChat(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function resetChat(sessionId: string): Promise<{ cleared: boolean }> {
  return request('/api/chat/reset', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId }),
  })
}

export function replaceChatHistory(
  sessionId: string,
  messages: Array<{ role: 'user' | 'assistant'; content: string }>,
): Promise<{ cleared: boolean }> {
  return request('/api/chat/history', {
    method: 'PUT',
    body: JSON.stringify({ session_id: sessionId, messages }),
  })
}

export function pingDatabase(): Promise<DatabasePingResponse> {
  return request('/api/db/ping')
}

export function fetchTables(schema: string): Promise<TablesResponse> {
  return request(`/api/db/tables?schema=${encodeURIComponent(schema)}`)
}
