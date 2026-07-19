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
        <strong>Query results</strong>
        <span>{rows.length} displayed row{rows.length === 1 ? '' : 's'}</span>
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
