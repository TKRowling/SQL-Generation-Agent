import { useState } from 'react'
import type { StoredMessage } from '../types/api'
import { DataTable } from './DataTable'
import { ReportInsights } from './ReportInsights'

interface MessageCardProps {
  message: StoredMessage
}

export function MessageCard({ message }: MessageCardProps) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)
  const embedded = message.sql ? null : extractEmbeddedSql(message.text)
  const displayedSql = message.sql ?? embedded?.sql ?? null
  const displayedText = embedded?.answer ?? message.text

  async function copySql(value: string) {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  return (
    <article className={`message-row ${isUser ? 'message-row-user' : 'message-row-assistant'}`}>
      {!isUser && <div className="avatar" aria-hidden="true">A</div>}
      <div className={`message-card ${message.error ? 'message-error' : ''}`}>
        {!isUser && (
          <div className="message-meta">
            <span>AskMe</span>
            {message.kind === 'data' && <span className="message-kind">Database</span>}
            {typeof message.rowCount === 'number' && message.rowCount > 0 && (
              <span className="message-count">{message.rowCount} row{message.rowCount === 1 ? '' : 's'}</span>
            )}
          </div>
        )}
        {displayedText && <p className="message-text">{displayedText}</p>}
        {!isUser && message.insights && message.insights.length > 0 && (
          <ReportInsights insights={message.insights} chart={message.chart ?? null} rows={message.rows ?? []} />
        )}
        {message.rows && message.rows.length > 1 && <DataTable rows={message.rows} />}
        {message.rows && message.rows.length === 1 && Object.keys(message.rows[0] ?? {}).length > 1 && (
          <DataTable rows={message.rows} />
        )}
        {displayedSql && (
          <SqlBlock
            sql={displayedSql}
            copied={copied}
            onCopy={() => void copySql(displayedSql)}
          />
        )}
        {!isUser && message.requestId && (
          <div className="response-trace">
            Request {message.requestId.slice(0, 8)}{typeof message.executionMs === 'number' ? ` · ${message.executionMs} ms` : ''}
          </div>
        )}
      </div>
    </article>
  )
}

function extractEmbeddedSql(text: string): { answer: string; sql: string } | null {
  const marker = /(?:the\s+)?sql\s+(?:script|query)(?:\s+used\s+to\s+retrieve\s+the\s+data)?\s*(?:is\s*:|:)/i
  const match = marker.exec(text)
  if (!match) return null

  const candidate = text.slice(match.index + match[0].length).trim()
  if (!/^select\b/i.test(candidate)) return null

  const semicolon = candidate.indexOf(';')
  const sql = (semicolon >= 0 ? candidate.slice(0, semicolon + 1) : candidate.replace(/\.$/, '')).trim()
  const before = text.slice(0, match.index).trim()
  const after = semicolon >= 0 ? candidate.slice(semicolon + 1).trim() : ''
  const answer = [before, after].filter(Boolean).join('\n\n')
  return { answer, sql }
}

interface SqlBlockProps {
  sql: string
  copied: boolean
  onCopy: () => void
}

function formatSql(sql: string): string {
  const structured = sql
    .trim()
    .replace(/\s+(FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|UNION|RETURNING)\s+/gi, '\n$1 ')
    .replace(/\s+(LEFT JOIN|RIGHT JOIN|INNER JOIN|FULL JOIN|CROSS JOIN|JOIN)\s+/gi, '\n$1 ')
    .replace(/\s+(AND|OR)\s+/gi, '\n  $1 ')
    .replace(/^SELECT\s+/i, 'SELECT\n    ')
    .replace(/;?$/, ';')

  let depth = 0
  let quoted = false
  let formatted = ''
  for (let index = 0; index < structured.length; index += 1) {
    const character = structured[index]
    if (character === "'" && structured[index - 1] !== '\\') quoted = !quoted
    if (!quoted && character === '(') depth += 1
    if (!quoted && character === ')') depth = Math.max(0, depth - 1)
    if (!quoted && depth === 0 && character === ',') {
      formatted += ',\n    '
      while (structured[index + 1] === ' ') index += 1
    } else {
      formatted += character
    }
  }
  return formatted
}

function SqlBlock({ sql, copied, onCopy }: SqlBlockProps) {
  const formatted = formatSql(sql)
  return (
    <section className="sql-panel" aria-label="Generated SQL">
      <header className="sql-panel-header">
        <span className="sql-language">sql</span>
        <button type="button" className="copy-button" onClick={onCopy} aria-label="Copy SQL">
          {copied ? (
            <span className="copy-confirmation">Copied</span>
          ) : (
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <rect x="8" y="8" width="11" height="11" rx="2" />
              <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
            </svg>
          )}
        </button>
      </header>
      <pre><code>{highlightSql(formatted)}</code></pre>
    </section>
  )
}

function highlightSql(sql: string) {
  const tokenPattern = /('(?:''|[^'])*')|\b(SELECT|FROM|WHERE|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|UNION|ALL|AS|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|AND|OR|NOT|IN|IS|NULL|ASC|DESC|DISTINCT|CASE|WHEN|THEN|ELSE|END|COUNT|SUM|AVG|MIN|MAX)\b|(\b\d+(?:\.\d+)?\b)/gi
  const parts = sql.split(tokenPattern)

  return parts.filter((part) => part !== undefined && part !== '').map((part, index) => {
    if (/^'(?:''|[^'])*'$/.test(part)) return <span className="sql-string" key={index}>{part}</span>
    if (/^\d+(?:\.\d+)?$/.test(part)) return <span className="sql-number" key={index}>{part}</span>
    if (/^(SELECT|FROM|WHERE|GROUP|BY|ORDER|HAVING|LIMIT|OFFSET|UNION|ALL|AS|JOIN|LEFT|RIGHT|INNER|OUTER|FULL|CROSS|ON|AND|OR|NOT|IN|IS|NULL|ASC|DESC|DISTINCT|CASE|WHEN|THEN|ELSE|END|COUNT|SUM|AVG|MIN|MAX)$/i.test(part)) {
      return <span className="sql-keyword" key={index}>{part.toUpperCase()}</span>
    }
    return part
  })
}
