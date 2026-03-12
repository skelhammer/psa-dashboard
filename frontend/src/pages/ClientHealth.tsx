import { useNavigate } from 'react-router-dom'
import { useClients } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import GlobalFilters from '../components/GlobalFilters'
import clsx from 'clsx'

function healthBadge(score: number, color: string) {
  const bgClass =
    color === 'green'
      ? 'bg-green-500/20 text-green-400 border-green-500/30'
      : color === 'yellow'
        ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
        : 'bg-red-500/20 text-red-400 border-red-500/30'

  return (
    <span className={clsx('px-2.5 py-0.5 rounded-full text-xs font-bold border tabular-nums', bgClass)}>
      {score}
    </span>
  )
}

export default function ClientHealth() {
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useClients(params)
  const navigate = useNavigate()

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  const clients = data?.clients || []
  const periodLabel = data?.date_range_label || ''

  return (
    <div className="space-y-6 animate-slide-up">
      <div>
        <h2 className="text-xl font-bold">Client Health</h2>
        <p className="text-sm text-gray-500 mt-1">
          Per-client service health scores, SLA compliance, and ticket metrics.
        </p>
      </div>

      <GlobalFilters />

      <div className="overflow-x-auto rounded-lg border border-zinc-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-zinc-900/80 border-b border-zinc-800">
              {[
                'Client Name', 'Health', 'Open', 'Closed', 'SLA %',
                'Avg FR', 'Avg Resolution', 'Hours'
              ].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {clients.map((client: any) => (
              <tr
                key={client.id}
                onClick={() => navigate(`/clients/${client.id}`)}
                className="hover:bg-zinc-800/30 transition-colors cursor-pointer"
              >
                <td className="px-3 py-2.5 font-medium text-brand-primary-light">{client.name}</td>
                <td className="px-3 py-2.5">
                  {healthBadge(client.health_score, client.health_color)}
                </td>
                <td className="px-3 py-2.5 tabular-nums">{client.open_tickets}</td>
                <td className="px-3 py-2.5 tabular-nums">{client.closed_period}</td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={clsx(
                    client.sla_compliance_pct >= 95 ? 'text-green-400' :
                    client.sla_compliance_pct >= 80 ? 'text-yellow-400' : 'text-red-400'
                  )}>
                    {client.sla_compliance_pct}%
                  </span>
                </td>
                <td className="px-3 py-2.5 tabular-nums text-xs">{formatDuration(client.avg_first_response_minutes)}</td>
                <td className="px-3 py-2.5 tabular-nums text-xs">{formatDuration(client.avg_resolution_minutes)}</td>
                <td className="px-3 py-2.5 tabular-nums">{client.billed_hours}h</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {periodLabel && (
        <p className="text-xs text-gray-500 text-right">{periodLabel}</p>
      )}
    </div>
  )
}
