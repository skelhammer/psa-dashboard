import clsx from 'clsx'

interface KpiCardProps {
  label: string
  value: string | number
  subtitle?: string
  colorClass?: string
  onClick?: () => void
  pctChange?: number | null
  changeDirection?: 'up-good' | 'down-good'
}

export default function KpiCard({ label, value, subtitle, colorClass, onClick, pctChange, changeDirection }: KpiCardProps) {
  let changeColor = 'text-gray-500'
  let arrow = ''
  if (pctChange != null && pctChange !== 0) {
    const isPositive = pctChange > 0
    arrow = isPositive ? '\u2191' : '\u2193'
    if (changeDirection === 'up-good') {
      changeColor = isPositive ? 'text-green-400' : 'text-red-400'
    } else if (changeDirection === 'down-good') {
      changeColor = isPositive ? 'text-red-400' : 'text-green-400'
    }
  }

  return (
    <div
      onClick={onClick}
      className={clsx(
        'card',
        onClick && 'card-hover',
        colorClass
      )}
    >
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-bold tabular-nums">{value}</p>
      {subtitle && <p className="text-xs text-gray-500 mt-1">{subtitle}</p>}
      {pctChange != null && pctChange !== 0 && (
        <p className={clsx('text-xs font-medium mt-1', changeColor)}>
          {arrow} {pctChange > 0 ? '+' : ''}{pctChange}% vs prev period
        </p>
      )}
    </div>
  )
}
