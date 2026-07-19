import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchTables, pingDatabase, resetChat, sendChat } from './api/client'
import { Composer } from './components/Composer'
import { MessageCard } from './components/MessageCard'
import { Sidebar } from './components/Sidebar'
import { TablesDialog } from './components/TablesDialog'
import type { DatabasePingResponse, StoredMessage } from './types/api'
import { getSessionId } from './utils/session'
import { clearMessages, loadMessages, saveMessages } from './utils/storage'

const welcomeMessage: StoredMessage = {
  id: 'welcome',
  role: 'assistant',
  text: 'Ask a question in plain language. I can query the live database for counts, lists, totals, breakdowns, recent records, and other read-only information.',
  kind: 'chat',
  createdAt: new Date().toISOString(),
}

function createId(): string {
  return crypto.randomUUID()
}

export default function App() {
  const sessionId = useMemo(getSessionId, [])
  const [messages, setMessages] = useState<StoredMessage[]>(() => {
    const stored = loadMessages()
    return stored.length ? stored : [welcomeMessage]
  })
  const [sending, setSending] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [dbStatus, setDbStatus] = useState<DatabasePingResponse | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [tablesOpen, setTablesOpen] = useState(false)
  const [tables, setTables] = useState<string[]>([])
  const [tablesLoading, setTablesLoading] = useState(false)
  const [tablesError, setTablesError] = useState('')
  const [queuedSuggestion, setQueuedSuggestion] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    saveMessages(messages)
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function refreshDatabaseStatus() {
    setLoadingStatus(true)
    try {
      setDbStatus(await pingDatabase())
    } catch (error) {
      setDbStatus({
        reachable: false,
        version: null,
        database: null,
        tables: null,
        message: error instanceof Error ? error.message : 'Database status check failed.',
      })
    } finally {
      setLoadingStatus(false)
    }
  }

  useEffect(() => {
    void refreshDatabaseStatus()
  }, [])

  async function send(message: string, forceData: boolean) {
    setSending(true)
    const userMessage: StoredMessage = {
      id: createId(),
      role: 'user',
      text: message,
      createdAt: new Date().toISOString(),
    }
    setMessages((current) => [...current, userMessage])

    try {
      const response = await sendChat({
        session_id: sessionId,
        message,
        force_data: forceData,
      })
      setMessages((current) => [
        ...current,
        {
          id: createId(),
          role: 'assistant',
          text: response.answer,
          kind: response.kind,
          rows: response.rows,
          rowCount: response.row_count,
          sql: response.sql,
          createdAt: new Date().toISOString(),
        },
      ])
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          id: createId(),
          role: 'assistant',
          text: error instanceof Error ? error.message : 'The request failed unexpectedly.',
          createdAt: new Date().toISOString(),
          error: true,
        },
      ])
    } finally {
      setSending(false)
    }
  }

  async function resetConversation() {
    setResetting(true)
    try {
      await resetChat(sessionId)
    } catch {
      // Clear the local display even if the backend is temporarily unreachable.
    } finally {
      clearMessages()
      setMessages([{ ...welcomeMessage, id: createId(), createdAt: new Date().toISOString() }])
      setResetting(false)
    }
  }

  async function showTables() {
    setTablesOpen(true)
    setTablesLoading(true)
    setTablesError('')
    try {
      const response = await fetchTables()
      setTables(response.tables)
    } catch (error) {
      setTablesError(error instanceof Error ? error.message : 'Could not load database tables.')
    } finally {
      setTablesLoading(false)
    }
  }

  function useSuggestion(suggestion: string) {
    setQueuedSuggestion(suggestion)
  }

  useEffect(() => {
    if (!queuedSuggestion || sending) return
    const value = queuedSuggestion
    setQueuedSuggestion('')
    void send(value, true)
  }, [queuedSuggestion, sending])

  return (
    <div className="app-shell">
      <Sidebar
        dbStatus={dbStatus}
        loadingStatus={loadingStatus}
        onRefreshStatus={() => void refreshDatabaseStatus()}
        onReset={() => void resetConversation()}
        onShowTables={() => void showTables()}
        onUseSuggestion={useSuggestion}
        resetting={resetting}
      />

      <main className="chat-main">
        <header className="mobile-header">
          <div className="brand-mark">A</div>
          <div className="mobile-title">
            <strong>AskMe</strong>
            <span>Read-only data assistant</span>
          </div>
          <span
            className={`mobile-status ${dbStatus?.reachable ? 'mobile-status-online' : 'mobile-status-offline'}`}
            title={dbStatus?.reachable ? 'Database connected' : 'Database unavailable'}
          />
          <button type="button" onClick={() => void showTables()} disabled={!dbStatus?.reachable}>Tables</button>
          <button type="button" onClick={() => void resetConversation()} disabled={resetting}>New</button>
        </header>

        <section className="chat-scroll" aria-live="polite">
          <div className="chat-inner">
            {messages.map((message) => <MessageCard key={message.id} message={message} />)}
            {sending && (
              <article className="message-row message-row-assistant">
                <div className="avatar" aria-hidden="true">A</div>
                <div className="message-card typing-card">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            )}
            <div ref={endRef} />
          </div>
        </section>

        <footer className="composer-area">
          <div className="composer-inner">
            <Composer disabled={sending} onSend={send} />
            <p className="safety-note">
              Read-only access. AI proposes SQL; the backend validates and executes it with a row cap.
            </p>
          </div>
        </footer>
      </main>

      <TablesDialog
        open={tablesOpen}
        loading={tablesLoading}
        tables={tables}
        error={tablesError}
        onClose={() => setTablesOpen(false)}
      />
    </div>
  )
}
