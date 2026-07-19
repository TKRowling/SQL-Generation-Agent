import type { DatabasePingResponse } from '../types/api'

interface SidebarProps {
  dbStatus: DatabasePingResponse | null
  loadingStatus: boolean
  onRefreshStatus: () => void
  onReset: () => void
  onShowTables: () => void
  onUseSuggestion: (value: string) => void
  resetting: boolean
}

const suggestions = [
  'How many documents were created in the last 7 days?',
  'Show the top 10 projects by document count.',
  'List the latest users and their status.',
  'Count documents grouped by status.',
]

export function Sidebar({
  dbStatus,
  loadingStatus,
  onRefreshStatus,
  onReset,
  onShowTables,
  onUseSuggestion,
  resetting,
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

        <button className="new-chat-button" type="button" onClick={onReset} disabled={resetting}>
          {resetting ? 'Resetting…' : '+ New conversation'}
        </button>

        <section className="sidebar-section">
          <div className="section-heading">Try asking</div>
          <div className="suggestion-list">
            {suggestions.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => onUseSuggestion(suggestion)}>
                {suggestion}
              </button>
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
