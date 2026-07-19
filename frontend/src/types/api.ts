export type ResultRow = Record<string, unknown>

export interface ChatRequest {
  session_id: string
  message: string
  force_data: boolean
}

export interface ChatResponse {
  kind: 'data' | 'chat'
  answer: string
  rows: ResultRow[]
  row_count: number
  sql: string | null
  insights: string[]
  chart: ChartSpec | null
  request_id: string | null
  execution_ms: number | null
}

export interface ChartSpec {
  type: 'bar' | 'line'
  title: string
  x_key: string
  y_keys: string[]
}

export interface DatabasePingResponse {
  reachable: boolean
  version: string | null
  database: string | null
  schema?: string | null
  tables: number | null
  message: string | null
}

export interface TablesResponse {
  tables: string[]
  count: number
}

export interface ApiErrorDetail {
  code?: string
  message?: string
}

export interface StoredMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  kind?: 'data' | 'chat'
  rows?: ResultRow[]
  rowCount?: number
  sql?: string | null
  createdAt: string
  error?: boolean
  insights?: string[]
  chart?: ChartSpec | null
  requestId?: string | null
  executionMs?: number | null
}

export interface StoredConversation {
  id: string
  title: string
  messages: StoredMessage[]
  createdAt: string
  updatedAt: string
}
