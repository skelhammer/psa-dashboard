import clsx from 'clsx'

interface KpiCardProps {
  label: string
  value: string | number
  subtitle?: string
  colorClass?: string
  onClick?: () => void
}

export default function KpiCard({ label, value, subtitle, colorClass, onClick }: KpiCardProps) {
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
    </div>
  )
}
