import { useEffect, useRef, useState } from 'react'
import { fetchTables, pingDatabase, resetChat, sendChat } from './api/client'
import { Composer } from './components/Composer'
import { MessageCard } from './components/MessageCard'
import { Sidebar } from './components/Sidebar'
import { TablesDialog } from './components/TablesDialog'
import type { DatabasePingResponse, StoredConversation, StoredMessage } from './types/api'
import { conversationTitle, loadConversationState, saveConversationState } from './utils/storage'

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
  const [conversationState, setConversationState] = useState(() => loadConversationState(welcomeMessage))
  const activeConversation = conversationState.conversations.find((item) => item.id === conversationState.activeId)
  const messages = activeConversation?.messages ?? [welcomeMessage]
  const [sending, setSending] = useState(false)
  const [dbStatus, setDbStatus] = useState<DatabasePingResponse | null>(null)
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [tablesOpen, setTablesOpen] = useState(false)
  const [tables, setTables] = useState<string[]>([])
  const [tablesLoading, setTablesLoading] = useState(false)
  const [tablesError, setTablesError] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    saveConversationState(conversationState)
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversationState])

  function updateConversation(id: string, update: (messages: StoredMessage[]) => StoredMessage[], title?: string) {
    setConversationState((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) => conversation.id === id ? {
        ...conversation,
        title: title ?? conversation.title,
        messages: update(conversation.messages).slice(-100),
        updatedAt: new Date().toISOString(),
      } : conversation),
    }))
  }

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
    const conversationId = conversationState.activeId
    setSending(true)
    const userMessage: StoredMessage = {
      id: createId(),
      role: 'user',
      text: message,
      createdAt: new Date().toISOString(),
    }
    const title = activeConversation?.title === 'New conversation' ? conversationTitle(message) : undefined
    updateConversation(conversationId, (current) => [...current, userMessage], title)

    try {
      const response = await sendChat({
        session_id: conversationId,
        message,
        force_data: forceData,
      })
      updateConversation(conversationId, (current) => [
        ...current,
        {
          id: createId(),
          role: 'assistant',
          text: response.answer,
          kind: response.kind,
          rows: response.rows,
          rowCount: response.row_count,
          sql: response.sql,
          insights: response.insights,
          chart: response.chart,
          requestId: response.request_id,
          executionMs: response.execution_ms,
          createdAt: new Date().toISOString(),
        },
      ])
    } catch (error) {
      updateConversation(conversationId, (current) => [
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

  function newConversation() {
    const now = new Date().toISOString()
    const conversation: StoredConversation = {
      id: createId(),
      title: 'New conversation',
      messages: [{ ...welcomeMessage, id: createId(), createdAt: now }],
      createdAt: now,
      updatedAt: now,
    }
    setConversationState((current) => ({
      activeId: conversation.id,
      conversations: [conversation, ...current.conversations].slice(0, 30),
    }))
  }

  function selectConversation(id: string) {
    if (!sending) setConversationState((current) => ({ ...current, activeId: id }))
  }

  function deleteConversation(id: string) {
    void resetChat(id).catch(() => undefined)
    setConversationState((current) => {
      const remaining = current.conversations.filter((conversation) => conversation.id !== id)
      if (remaining.length) return { conversations: remaining, activeId: current.activeId === id ? remaining[0]!.id : current.activeId }
      const now = new Date().toISOString()
      const replacement: StoredConversation = { id: createId(), title: 'New conversation', messages: [{ ...welcomeMessage, id: createId(), createdAt: now }], createdAt: now, updatedAt: now }
      return { conversations: [replacement], activeId: replacement.id }
    })
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

  return (
    <div className="app-shell">
      <Sidebar
        dbStatus={dbStatus}
        loadingStatus={loadingStatus}
        onRefreshStatus={() => void refreshDatabaseStatus()}
        onNewConversation={newConversation}
        onSelectConversation={selectConversation}
        onDeleteConversation={deleteConversation}
        onShowTables={() => void showTables()}
        resetting={false}
        conversations={conversationState.conversations}
        activeConversationId={conversationState.activeId}
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
          <button type="button" onClick={newConversation}>New</button>
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
