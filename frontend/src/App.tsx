import { useEffect, useRef, useState } from 'react'
import { fetchTables, pingDatabase, replaceChatHistory, resetChat, sendChat } from './api/client'
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

const SIDEBAR_KEY = 'askme.sidebar-open'

function createId(): string {
  return crypto.randomUUID()
}

export default function App() {
  const [conversationState, setConversationState] = useState(() => loadConversationState(welcomeMessage))
  const activeConversation = conversationState.conversations.find((item) => item.id === conversationState.activeId)
  const messages = activeConversation?.messages ?? [welcomeMessage]
  const [sending, setSending] = useState(false)
  const [dbStatus, setDbStatus] = useState<DatabasePingResponse | null>(null)
  const selectedSchema = activeConversation?.schema
    ?? dbStatus?.schema
    ?? dbStatus?.schemas[0]
    ?? ''
  const [loadingStatus, setLoadingStatus] = useState(true)
  const [tablesOpen, setTablesOpen] = useState(false)
  const [tables, setTables] = useState<string[]>([])
  const [tablesLoading, setTablesLoading] = useState(false)
  const [tablesError, setTablesError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    const saved = localStorage.getItem(SIDEBAR_KEY)
    if (saved !== null) return saved === 'true'
    return !window.matchMedia('(max-width: 820px)').matches
  })
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    saveConversationState(conversationState)
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversationState])

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, String(sidebarOpen))
  }, [sidebarOpen])

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
        schemas: [],
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
        schema: selectedSchema,
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
      schema: selectedSchema || undefined,
    }
    setConversationState((current) => ({
      activeId: conversation.id,
      conversations: [conversation, ...current.conversations].slice(0, 30),
    }))
    if (window.matchMedia('(max-width: 820px)').matches) setSidebarOpen(false)
  }

  function selectConversation(id: string) {
    if (!sending) {
      setConversationState((current) => ({ ...current, activeId: id }))
      if (window.matchMedia('(max-width: 820px)').matches) setSidebarOpen(false)
    }
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

  function renameConversation(id: string, title: string) {
    setConversationState((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) => conversation.id === id
        ? { ...conversation, title, updatedAt: new Date().toISOString() }
        : conversation),
    }))
  }

  async function editQuestion(messageId: string, text: string) {
    if (sending || !activeConversation) return
    const messageIndex = activeConversation.messages.findIndex((message) => message.id === messageId)
    if (messageIndex < 0 || activeConversation.messages[messageIndex]?.role !== 'user') return

    const conversationId = activeConversation.id
    const prefix = activeConversation.messages.slice(0, messageIndex)
    const editedMessage: StoredMessage = {
      ...activeConversation.messages[messageIndex]!,
      text,
      createdAt: new Date().toISOString(),
    }
    const firstUserIndex = prefix.findIndex((message) => message.role === 'user')
    const context = (firstUserIndex >= 0 ? prefix.slice(firstUserIndex) : [])
      .filter((message) => !message.error)
      .map((message) => ({ role: message.role, content: message.text }))

    setSending(true)
    setConversationState((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) => conversation.id === conversationId
        ? {
            ...conversation,
            messages: [...prefix, editedMessage],
            updatedAt: new Date().toISOString(),
          }
        : conversation),
    }))

    try {
      await replaceChatHistory(conversationId, context)
      const response = await sendChat({
        session_id: conversationId,
        message: text,
        force_data: false,
        schema: selectedSchema,
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
          text: error instanceof Error ? error.message : 'The updated request failed unexpectedly.',
          createdAt: new Date().toISOString(),
          error: true,
        },
      ])
    } finally {
      setSending(false)
    }
  }

  function selectSchema(schema: string) {
    if (!schema || schema === selectedSchema || sending) return
    void resetChat(conversationState.activeId).catch(() => undefined)
    setConversationState((current) => ({
      ...current,
      conversations: current.conversations.map((conversation) =>
        conversation.id === current.activeId
          ? {
              ...conversation,
              schema,
              messages: [{
                ...welcomeMessage,
                id: createId(),
                text: `Schema changed to ${schema}. Ask a question about this schema.`,
                createdAt: new Date().toISOString(),
              }],
              updatedAt: new Date().toISOString(),
            }
          : conversation),
    }))
  }

  async function showTables() {
    setTablesOpen(true)
    setTablesLoading(true)
    setTablesError('')
    try {
      const response = await fetchTables(selectedSchema)
      setTables(response.tables)
    } catch (error) {
      setTablesError(error instanceof Error ? error.message : 'Could not load database tables.')
    } finally {
      setTablesLoading(false)
    }
  }

  return (
    <div className={`app-shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
      {sidebarOpen && <button className="sidebar-overlay" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close sidebar" />}
      <div className="sidebar-slot">
        <Sidebar
          dbStatus={dbStatus}
          loadingStatus={loadingStatus}
          onRefreshStatus={() => void refreshDatabaseStatus()}
          onNewConversation={newConversation}
          onSelectConversation={selectConversation}
          onDeleteConversation={deleteConversation}
          onRenameConversation={renameConversation}
          onShowTables={() => void showTables()}
          onCollapse={() => setSidebarOpen(false)}
          selectedSchema={selectedSchema}
          onSelectSchema={selectSchema}
          resetting={false}
          conversations={conversationState.conversations}
          activeConversationId={conversationState.activeId}
        />
      </div>

      <main className="chat-main">
        {!sidebarOpen && (
          <button className="sidebar-open-button" type="button" onClick={() => setSidebarOpen(true)} aria-label="Show sidebar" title="Show sidebar">
            <span aria-hidden="true">☰</span>
          </button>
        )}
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
          <button type="button" onClick={() => setSidebarOpen((open) => !open)}>History</button>
          <button type="button" onClick={() => void showTables()} disabled={!dbStatus?.reachable}>Tables</button>
          <button type="button" onClick={newConversation}>New</button>
        </header>

        <header className="workspace-header">
          <div className="workspace-heading">
            <span className="workspace-eyebrow">Conversation</span>
            <strong>{activeConversation?.title ?? 'New conversation'}</strong>
          </div>
          <div className="workspace-context">
            <span className={`context-status ${dbStatus?.reachable ? 'context-status-online' : ''}`} aria-hidden="true" />
            <span>{dbStatus?.reachable ? 'Connected' : 'Offline'}</span>
            <span className="context-separator" aria-hidden="true" />
            <span>Schema</span>
            <strong>{selectedSchema || 'Not selected'}</strong>
          </div>
        </header>

        <section className="chat-scroll" aria-live="polite">
          <div className="chat-inner">
            {messages.map((message) => (
              <MessageCard
                key={message.id}
                message={message}
                onEdit={message.role === 'user' ? editQuestion : undefined}
                editingDisabled={sending}
              />
            ))}
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
            <Composer disabled={sending} onSend={send} schema={selectedSchema} />
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
