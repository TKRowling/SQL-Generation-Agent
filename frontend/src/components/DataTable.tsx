import type { ResultRow } from '../types/api'

interface DataTableProps {
  rows: ResultRow[]
}

function humanize(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

function formatValue(value: unknown, key: string): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return /(^id$|_id$)/i.test(key) ? String(value) : value.toLocaleString('en-US')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function DataTable({ rows }: DataTableProps) {
  if (rows.length === 0) return null

  const initialColumns = Object.keys(rows[0] ?? {})
  const nonIdColumns = initialColumns.filter((column) => !/^id$/i.test(column))
  const columns = nonIdColumns.length > 0 ? nonIdColumns : initialColumns

  return (
    <div className="result-table-section">
      <div className="result-table-heading">
        <div><strong>Query results</strong><span>{rows.length} displayed row{rows.length === 1 ? '' : 's'}</span></div>
        <div className="export-actions">
          <button type="button" onClick={() => downloadCsv(rows)}>CSV</button>
          <button type="button" onClick={() => downloadExcel(rows)}>Excel</button>
          <button type="button" onClick={() => printReport(rows)}>PDF</button>
        </div>
      </div>
      <div className="result-table-wrap" role="region" aria-label="Database results" tabIndex={0}>
        <table className="result-table">
        <thead>
          <tr>
            <th scope="col">#</th>
            {columns.map((column) => (
              <th scope="col" key={column}>{humanize(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${JSON.stringify(row)}`}>
              <td>{rowIndex + 1}</td>
              {columns.map((column) => (
                <td key={column} title={formatValue(row[column], column)}>
                  {formatValue(row[column], column)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </div>
  )
}

function escapeCell(value: unknown): string {
  const text = value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
  return `"${text.replace(/"/g, '""')}"`
}

function saveBlob(content: BlobPart, type: string, filename: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function downloadCsv(rows: ResultRow[]) {
  const columns = Object.keys(rows[0] ?? {})
  const csv = [columns.map(escapeCell).join(','), ...rows.map((row) => columns.map((key) => escapeCell(row[key])).join(','))].join('\n')
  saveBlob(`\uFEFF${csv}`, 'text/csv;charset=utf-8', 'askme-report.csv')
}

function downloadExcel(rows: ResultRow[]) {
  const columns = Object.keys(rows[0] ?? {})
  const body = rows.map((row) => `<tr>${columns.map((key) => `<td>${html(row[key])}</td>`).join('')}</tr>`).join('')
  const table = `<table><thead><tr>${columns.map((key) => `<th>${html(key)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`
  saveBlob(table, 'application/vnd.ms-excel', 'askme-report.xls')
}

function printReport(rows: ResultRow[]) {
  const columns = Object.keys(rows[0] ?? {})
  const popup = window.open('', '_blank', 'width=1000,height=700')
  if (!popup) return
  const body = rows.map((row) => `<tr>${columns.map((key) => `<td>${html(row[key])}</td>`).join('')}</tr>`).join('')
  popup.document.write(`<title>AskMe Report</title><style>body{font-family:Arial;padding:32px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f1f4f8}</style><h1>AskMe Report</h1><table><thead><tr>${columns.map((key) => `<th>${html(key)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`)
  popup.document.close()
  popup.print()
}

function html(value: unknown): string {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character] ?? character)
}
