interface TablesDialogProps {
  open: boolean
  loading: boolean
  tables: string[]
  error: string
  onClose: () => void
}

export function TablesDialog({ open, loading, tables, error, onClose }: TablesDialogProps) {
  if (!open) return null

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tables-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="tables-title">Database tables</h2>
            <p>{tables.length ? `${tables.length} tables available` : 'Live schema inspection'}</p>
          </div>
          <button type="button" className="dialog-close" onClick={onClose} aria-label="Close">×</button>
        </header>
        <div className="dialog-content">
          {loading && <p>Loading tables…</p>}
          {error && <p className="dialog-error">{error}</p>}
          {!loading && !error && (
            <div className="table-name-grid">
              {tables.map((table) => <code key={table}>{table}</code>)}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
