import clsx from 'clsx'
import { TrendingUp, TrendingDown } from 'lucide-react'

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
  let isPositive = false
  let isGood = false
  if (pctChange != null && pctChange !== 0) {
    isPositive = pctChange > 0
    if (changeDirection === 'up-good') {
      isGood = isPositive
    } else if (changeDirection === 'down-good') {
      isGood = !isPositive
    }
    changeColor = isGood ? 'text-emerald-400' : 'text-red-400'
  }

  return (
    <div
      onClick={onClick}
      className={clsx(
        'group relative overflow-hidden rounded-xl border p-5 transition-all duration-200 animate-fade-in',
        'bg-[#111113] shadow-lg shadow-black/25 hover:shadow-xl hover:-translate-y-0.5',
        onClick && 'cursor-pointer active:translate-y-0',
        colorClass || 'border-white/[0.08] hover:border-white/[0.15]',
      )}
    >
      {/* Subtle top accent line */}
      <div className={clsx(
        'absolute top-0 left-0 right-0 h-[1px] opacity-0 group-hover:opacity-100 transition-opacity duration-300',
        'bg-gradient-to-r from-transparent via-brand-primary/40 to-transparent'
      )} />
      {/* Hover glow */}
      <div className="absolute inset-0 bg-gradient-to-br from-brand-primary/[0.04] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
      <div className="relative">
        <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2.5">{label}</p>
        <p className="text-2xl font-bold tabular-nums tracking-tight text-white">{value}</p>
        {subtitle && <p className="text-[11px] text-gray-500 mt-2">{subtitle}</p>}
        {pctChange != null && pctChange !== 0 && (
          <div className={clsx('flex items-center gap-1 mt-2', changeColor)}>
            {isPositive
              ? <TrendingUp size={13} strokeWidth={2.5} />
              : <TrendingDown size={13} strokeWidth={2.5} />
            }
            <span className="text-xs font-semibold tabular-nums">
              {pctChange > 0 ? '+' : ''}{pctChange}% vs prev
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
