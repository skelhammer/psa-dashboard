import { useNavigate } from 'react-router-dom'
import { useTechnicians } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import GlobalFilters from '../components/GlobalFilters'
import clsx from 'clsx'

function utilizationColor(pct: number): string {
  if (pct >= 60 && pct <= 80) return 'text-green-400'
  if ((pct >= 80 && pct <= 90) || pct < 40) return 'text-yellow-400'
  if (pct > 90) return 'text-red-400'
  return 'text-gray-400'
}

export default function Technicians() {
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useTechnicians(params)
  const navigate = useNavigate()

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  const techs = data?.technicians || []
  const periodLabel = data?.date_range_label || ''

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold">Technician Performance</h2>
        <p className="text-sm text-gray-500 mt-1">
          Per-tech metrics including response times, worklog hours, utilization, and SLA compliance.
        </p>
      </div>

      <GlobalFilters />

      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-900/80 border-b border-gray-800">
              {[
                'Name', 'Open', 'Closed', 'Avg FR',
                'Avg Res', 'FR Viol', 'Res Viol', 'Hours',
                'Util %', 'Stale', 'Reopened', 'Billing %'
              ].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {techs.map((tech: any) => (
              <tr
                key={tech.id}
                onClick={() => navigate(`/technicians/${tech.id}`)}
                className="hover:bg-gray-800/30 transition-colors cursor-pointer"
              >
                <td className="px-3 py-2.5 font-medium text-brand-gold">{tech.name}</td>
                <td className="px-3 py-2.5 tabular-nums">{tech.open_tickets}</td>
                <td className="px-3 py-2.5 tabular-nums">{tech.closed_period}</td>
                <td className="px-3 py-2.5 tabular-nums text-xs">{formatDuration(tech.avg_first_response_minutes)}</td>
                <td className="px-3 py-2.5 tabular-nums text-xs">{formatDuration(tech.avg_resolution_minutes)}</td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={tech.fr_violations > 0 ? 'text-red-400' : ''}>
                    {tech.fr_violations} ({tech.fr_violation_pct}%)
                  </span>
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={tech.res_violations > 0 ? 'text-red-400' : ''}>
                    {tech.res_violations} ({tech.res_violation_pct}%)
                  </span>
                </td>
                <td className="px-3 py-2.5 tabular-nums">{tech.worklog_hours}h</td>
                <td className={clsx('px-3 py-2.5 tabular-nums font-medium', utilizationColor(tech.utilization_pct))}>
                  {tech.utilization_pct}%
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={tech.stale_tickets > 0 ? 'text-yellow-400' : ''}>{tech.stale_tickets}</span>
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={tech.reopened_tickets > 0 ? 'text-yellow-400' : ''}>{tech.reopened_tickets}</span>
                </td>
                <td className="px-3 py-2.5 tabular-nums">
                  <span className={tech.billing_compliance_pct < 100 ? 'text-red-400' : 'text-green-400'}>
                    {tech.billing_compliance_pct}%
                  </span>
                </td>
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
