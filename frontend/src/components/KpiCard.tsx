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
      changeColor = isPositive ? 'text-emerald-400' : 'text-red-400'
    } else if (changeDirection === 'down-good') {
      changeColor = isPositive ? 'text-red-400' : 'text-emerald-400'
    }
  }

  return (
    <div
      onClick={onClick}
      className={clsx(
        'group relative overflow-hidden rounded-xl border p-4 transition-all duration-200 animate-fade-in',
        'bg-[#111113]/80 backdrop-blur-sm shadow-lg shadow-black/20',
        onClick && 'cursor-pointer hover:shadow-xl hover:-translate-y-0.5',
        colorClass || 'border-white/[0.06] hover:border-brand-primary/30',
      )}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-brand-primary/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
      <div className="relative">
        <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2">{label}</p>
        <p className="text-2xl font-bold tabular-nums tracking-tight">{value}</p>
        {subtitle && <p className="text-[11px] text-gray-500 mt-1.5">{subtitle}</p>}
        {pctChange != null && pctChange !== 0 && (
          <p className={clsx('text-xs font-semibold mt-1.5 tabular-nums', changeColor)}>
            {arrow} {pctChange > 0 ? '+' : ''}{pctChange}% vs prev
          </p>
        )}
      </div>
    </div>
  )
}
