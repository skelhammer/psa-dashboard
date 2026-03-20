import { AlertTriangle, AlertCircle, Info } from 'lucide-react'
import clsx from 'clsx'

interface InsightCardProps {
  type: 'critical' | 'warning' | 'info'
  title: string
  description: string
}

const iconMap = {
  critical: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

const colorMap = {
  critical: 'border-red-500/30 bg-red-500/5',
  warning: 'border-yellow-500/30 bg-yellow-500/5',
  info: 'border-blue-500/30 bg-blue-500/5',
}

const iconColorMap = {
  critical: 'text-red-400',
  warning: 'text-yellow-400',
  info: 'text-blue-400',
}

export default function InsightCard({ type, title, description }: InsightCardProps) {
  const Icon = iconMap[type]
  return (
    <div className={clsx(
      'rounded-xl border p-4 animate-fade-in',
      colorMap[type],
    )}>
      <div className="flex items-start gap-3">
        <Icon size={18} className={clsx('mt-0.5 shrink-0', iconColorMap[type])} />
        <div>
          <p className="text-sm font-semibold text-gray-200">{title}</p>
          <p className="text-xs text-gray-400 mt-0.5">{description}</p>
        </div>
      </div>
    </div>
  )
}
