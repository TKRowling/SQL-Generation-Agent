import { useState } from 'react'
import type { DatabasePingResponse, StoredConversation } from '../types/api'

interface SidebarProps {
  dbStatus: DatabasePingResponse | null
  loadingStatus: boolean
  onRefreshStatus: () => void
  onNewConversation: () => void
  onSelectConversation: (id: string) => void
  onDeleteConversation: (id: string) => void
  onRenameConversation: (id: string, title: string) => void
  onShowTables: () => void
  onCollapse: () => void
  selectedSchema: string
  onSelectSchema: (schema: string) => void
  resetting: boolean
  conversations: StoredConversation[]
  activeConversationId: string
}

export function Sidebar({
  dbStatus,
  loadingStatus,
  onRefreshStatus,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  onShowTables,
  onCollapse,
  selectedSchema,
  onSelectSchema,
  resetting,
  conversations,
  activeConversationId,
}: SidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const statusClass = dbStatus?.reachable ? 'status-online' : 'status-offline'
  const schemaCount = dbStatus?.schemas.length ?? 0
  const statusLabel = loadingStatus
    ? 'Checking database...'
    : dbStatus?.reachable
      ? `Connected · ${schemaCount} ${schemaCount === 1 ? 'schema' : 'schemas'}`
      : 'Database unavailable'

  function beginRename(conversation: StoredConversation) {
    setEditingId(conversation.id)
    setDraftTitle(conversation.title)
  }

  function finishRename(id: string) {
    const title = draftTitle.replace(/\s+/g, ' ').trim().slice(0, 80)
    if (title) onRenameConversation(id, title)
    setEditingId(null)
    setDraftTitle('')
  }

  return (
    <aside className="sidebar">
      <div>
        <div className="brand">
          <div className="brand-mark">A</div>
          <div className="brand-copy">
            <h1>AskMe</h1>
            <p>Read-only data assistant</p>
          </div>
          <button className="sidebar-collapse" type="button" onClick={onCollapse} aria-label="Hide sidebar" title="Hide sidebar">
            <span aria-hidden="true">‹</span>
          </button>
        </div>

        <button className="new-chat-button" type="button" onClick={onNewConversation} disabled={resetting}>
          {resetting ? 'Resetting...' : '+ New conversation'}
        </button>

        <section className="sidebar-section history-section">
          <div className="section-heading">History</div>
          <div className="history-list">
            {conversations.map((conversation) => (
              <div className={`history-item ${conversation.id === activeConversationId ? 'history-item-active' : ''}`} key={conversation.id}>
                {editingId === conversation.id ? (
                  <form className="history-rename-form" onSubmit={(event) => { event.preventDefault(); finishRename(conversation.id) }}>
                    <input
                      autoFocus
                      value={draftTitle}
                      onChange={(event) => setDraftTitle(event.target.value)}
                      onBlur={() => finishRename(conversation.id)}
                      onKeyDown={(event) => {
                        if (event.key === 'Escape') {
                          event.preventDefault()
                          setEditingId(null)
                        }
                      }}
                      aria-label="Conversation name"
                      maxLength={80}
                    />
                  </form>
                ) : (
                  <button
                    className="history-select"
                    type="button"
                    onClick={() => onSelectConversation(conversation.id)}
                    onDoubleClick={() => beginRename(conversation)}
                    title={conversation.title}
                  >
                    <span>{conversation.title}</span>
                    <small>{new Date(conversation.updatedAt).toLocaleDateString()}</small>
                  </button>
                )}
                <div className="history-actions">
                  <button className="history-action history-rename" type="button" onClick={() => beginRename(conversation)} aria-label={`Rename ${conversation.title}`} title="Rename">
                    <span aria-hidden="true">✎</span>
                  </button>
                  <button className="history-action history-delete" type="button" onClick={() => onDeleteConversation(conversation.id)} aria-label={`Delete ${conversation.title}`} title="Delete">
                    <span aria-hidden="true">×</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="database-panel">
        <label className="schema-picker">
          <span>Active schema</span>
          <select value={selectedSchema} onChange={(event) => onSelectSchema(event.target.value)} disabled={!dbStatus?.schemas.length}>
            {(dbStatus?.schemas ?? []).map((schema) => <option key={schema} value={schema}>{schema}</option>)}
          </select>
        </label>
        <div className="database-status-row">
          <span className={`status-dot ${statusClass}`} aria-hidden="true" />
          <div>
            <strong>{statusLabel}</strong>
            {dbStatus?.reachable && (
              <small>{dbStatus.database}{selectedSchema ? ` · ${selectedSchema}` : ''} · PostgreSQL {dbStatus.version}</small>
            )}
            {!dbStatus?.reachable && dbStatus?.message && <small>{dbStatus.message}</small>}
          </div>
        </div>
        <div className="database-actions">
          <button type="button" onClick={onRefreshStatus}>Refresh</button>
          <button type="button" onClick={onShowTables} disabled={!dbStatus?.reachable}>Tables</button>
        </div>
      </section>
    </aside>
  )
}
