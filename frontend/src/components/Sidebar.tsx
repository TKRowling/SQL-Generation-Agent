import type { DatabasePingResponse, StoredConversation } from '../types/api'

interface SidebarProps {
  dbStatus: DatabasePingResponse | null
  loadingStatus: boolean
  onRefreshStatus: () => void
  onNewConversation: () => void
  onSelectConversation: (id: string) => void
  onDeleteConversation: (id: string) => void
  onShowTables: () => void
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
  onShowTables,
  resetting,
  conversations,
  activeConversationId,
}: SidebarProps) {
  const statusClass = dbStatus?.reachable ? 'status-online' : 'status-offline'
  const statusLabel = loadingStatus
    ? 'Checking database…'
    : dbStatus?.reachable
      ? `Connected · ${dbStatus.tables ?? 0} tables`
      : 'Database unavailable'

  return (
    <aside className="sidebar">
      <div>
        <div className="brand">
          <div className="brand-mark">A</div>
          <div>
            <h1>AskMe</h1>
            <p>Read-only data assistant</p>
          </div>
        </div>

        <button className="new-chat-button" type="button" onClick={onNewConversation} disabled={resetting}>
          {resetting ? 'Resetting…' : '+ New conversation'}
        </button>

        <section className="sidebar-section history-section">
          <div className="section-heading">History</div>
          <div className="history-list">
            {conversations.map((conversation) => (
              <div className={`history-item ${conversation.id === activeConversationId ? 'history-item-active' : ''}`} key={conversation.id}>
                <button className="history-select" type="button" onClick={() => onSelectConversation(conversation.id)} title={conversation.title}>
                  <span>{conversation.title}</span>
                  <small>{new Date(conversation.updatedAt).toLocaleDateString()}</small>
                </button>
                <button className="history-delete" type="button" onClick={() => onDeleteConversation(conversation.id)} aria-label={`Delete ${conversation.title}`}>×</button>
              </div>
            ))}
          </div>
        </section>

      </div>

      <section className="database-panel">
        <div className="database-status-row">
          <span className={`status-dot ${statusClass}`} aria-hidden="true" />
          <div>
            <strong>{statusLabel}</strong>
            {dbStatus?.reachable && (
              <small>{dbStatus.database}{dbStatus.schema ? ` · ${dbStatus.schema}` : ""} · PostgreSQL {dbStatus.version}</small>
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
