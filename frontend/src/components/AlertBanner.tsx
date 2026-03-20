import { useAlerts } from '../api/hooks'
import { AlertCircle, AlertTriangle, X } from 'lucide-react'
import clsx from 'clsx'
import { useState } from 'react'

export default function AlertBanner() {
  const { data } = useAlerts()
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())

  const alerts = (data?.alerts || []).filter(
    (a: any) => a.type === 'critical' && !dismissed.has(a.title)
  )

  if (alerts.length === 0) return null

  return (
    <div className="border-b border-red-500/30 bg-red-500/10 px-6 py-2">
      {alerts.map((alert: any, i: number) => (
        <div key={i} className="flex items-center justify-between gap-3 py-1">
          <div className="flex items-center gap-2">
            <AlertCircle size={14} className="text-red-400 shrink-0" />
            <span className="text-xs font-semibold text-red-300">{alert.title}</span>
            <span className="text-xs text-red-400/70">{alert.description}</span>
          </div>
          <button
            onClick={() => setDismissed(prev => new Set(prev).add(alert.title))}
            className="text-red-400/50 hover:text-red-300 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}
