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
}
