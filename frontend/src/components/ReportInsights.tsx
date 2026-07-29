import type { ChartSpec, ResultRow } from '../types/api'

interface Props {
  insights: string[]
  chart: ChartSpec | null
  rows: ResultRow[]
}

export function ReportInsights({ insights, chart, rows }: Props) {
  return (
    <section className="insight-panel">
      <div className="insight-heading">Executive insights</div>
      <ul>{insights.map((insight) => <li key={insight}>{insight}</li>)}</ul>
      {chart && <MiniChart chart={chart} rows={rows.slice(0, 12)} />}
    </section>
  )
}

function MiniChart({ chart, rows }: { chart: ChartSpec; rows: ResultRow[] }) {
  const key = chart.y_keys[0]
  if (!key) return null
  if (chart.type === 'pie') return <PieChart chart={chart} rows={rows.slice(0, 8)} valueKey={key} />
  const values = rows.map((row) => Number(row[key])).filter(Number.isFinite)
  if (values.length < 2) return null
  const max = Math.max(...values, 1)
  const width = 640
  const height = 190
  const bottom = 160
  const slot = width / values.length
  const points = values.map((value, index) => `${index * slot + slot / 2},${bottom - (value / max) * 125}`).join(' ')

  return (
    <div className="mini-chart" role="img" aria-label={chart.title}>
      <div className="chart-title">{chart.title}</div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <line className="chart-axis" x1="0" y1={bottom} x2={width} y2={bottom} />
        {chart.type === 'line' ? (
          <>
            <polyline className="chart-line" points={points} />
            {points.split(' ').map((point) => {
              const [cx, cy] = point.split(',')
              return <circle className="chart-dot" key={point} cx={cx} cy={cy} r="3" />
            })}
          </>
        ) : values.map((value, index) => {
          const barHeight = (value / max) * 125
          return <rect className="chart-bar" key={index} x={index * slot + slot * 0.18} y={bottom - barHeight} width={slot * 0.64} height={barHeight} rx="3" />
        })}
      </svg>
      <div className="chart-labels">
        {rows.map((row, index) => <span key={index}>{String(row[chart.x_key] ?? '')}</span>)}
      </div>
    </div>
  )
}

const PIE_COLORS = ['#466fd0', '#25a18e', '#f0a44b', '#8a63d2', '#e26178', '#57a7d8', '#7cab55', '#c47b45']

function PieChart({ chart, rows, valueKey }: { chart: ChartSpec; rows: ResultRow[]; valueKey: string }) {
  const slices = rows
    .map((row, index) => ({
      label: String(row[chart.x_key] ?? `Category ${index + 1}`),
      value: Number(row[valueKey]),
      color: PIE_COLORS[index % PIE_COLORS.length]!,
    }))
    .filter((slice) => Number.isFinite(slice.value) && slice.value >= 0)
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)
  if (slices.length < 2 || total <= 0) return null

  let cursor = 0
  const stops = slices.map((slice) => {
    const start = cursor
    cursor += slice.value / total * 100
    return `${slice.color} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`
  })

  return (
    <div className="mini-chart pie-chart" role="img" aria-label={chart.title}>
      <div className="chart-title">{chart.title}</div>
      <div className="pie-layout">
        <div className="pie-graphic" style={{ background: `conic-gradient(${stops.join(', ')})` }}>
          <div className="pie-center">
            <strong>{formatCompact(total)}</strong>
            <span>Total</span>
          </div>
        </div>
        <div className="pie-legend">
          {slices.map((slice) => (
            <div className="pie-legend-item" key={slice.label}>
              <span className="pie-swatch" style={{ background: slice.color }} />
              <span className="pie-label" title={slice.label}>{slice.label}</span>
              <strong>{(slice.value / total * 100).toFixed(1)}%</strong>
              <small>{slice.value.toLocaleString('en-US')}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function formatCompact(value: number): string {
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}
