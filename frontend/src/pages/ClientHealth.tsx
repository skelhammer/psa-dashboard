import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useClients, useClientProfitability } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import GlobalFilters from '../components/GlobalFilters'
import ChartCard from '../components/ChartCard'
import clsx from 'clsx'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Line, ComposedChart, Cell,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

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
  const { data: profitData } = useClientProfitability(params)
  const navigate = useNavigate()
  const [tab, setTab] = useState<'health' | 'profitability'>('health')

  if (isLoading && !data) return <div className="text-gray-500">Loading...</div>

  const clients = data?.clients || []
  const periodLabel = data?.date_range_label || ''
  const profClients = profitData?.clients || []
  const techCost = profitData?.tech_cost_per_hour || 55

  // Pareto: top 20 clients by hours
  const paretoData = profClients.slice(0, 20).map((c: any) => ({
    name: c.name.length > 18 ? c.name.substring(0, 18) + '...' : c.name,
    hours: c.hours_consumed,
    cumulative_pct: c.cumulative_hours_pct,
  }))

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Client Health</h2>
          <p className="text-sm text-gray-500 mt-1">
            Per-client service health scores, SLA compliance, and profitability.
          </p>
        </div>
      </div>

      <GlobalFilters />

      {/* Tab Switcher */}
      <div className="flex gap-1 bg-white/[0.03] rounded-lg p-1 w-fit">
        <button
          onClick={() => setTab('health')}
          className={clsx(
            'px-4 py-1.5 rounded-md text-xs font-medium transition-all',
            tab === 'health'
              ? 'bg-brand-primary/20 text-brand-primary-light border border-brand-primary/20'
              : 'text-gray-500 hover:text-gray-300 border border-transparent'
          )}
        >
          Health Scores
        </button>
        <button
          onClick={() => setTab('profitability')}
          className={clsx(
            'px-4 py-1.5 rounded-md text-xs font-medium transition-all',
            tab === 'profitability'
              ? 'bg-brand-primary/20 text-brand-primary-light border border-brand-primary/20'
              : 'text-gray-500 hover:text-gray-300 border border-transparent'
          )}
        >
          Profitability
        </button>
      </div>

      {tab === 'health' && (
        <>
          <div className="overflow-x-auto rounded-xl border border-white/[0.08] shadow-lg shadow-black/20">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#111113] border-b border-white/[0.08]">
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
        </>
      )}

      {tab === 'profitability' && (
        <>
          {/* Pareto Chart */}
          {paretoData.length > 0 && (
            <ChartCard title="Top Clients by Hours Consumed (Pareto)" exportData={paretoData} exportFilename="client_pareto">
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={paretoData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
                  <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={160} />
                  <Tooltip {...tooltipStyle} />
                  <Bar dataKey="hours" radius={[0, 4, 4, 0]} name="Hours">
                    {paretoData.map((_: any, i: number) => (
                      <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Bar>
                </ComposedChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Profitability Table */}
          <div className="overflow-x-auto rounded-xl border border-white/[0.08] shadow-lg shadow-black/20">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-[#111113] border-b border-white/[0.08]">
                  {[
                    'Client', 'Type', 'Contract $/mo', 'Hours', 'Tickets',
                    'Service Cost', 'EHR', 'Margin', 'Margin %'
                  ].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {profClients.map((c: any) => (
                  <tr
                    key={c.id}
                    onClick={() => navigate(`/clients/${c.id}`)}
                    className="hover:bg-zinc-800/30 transition-colors cursor-pointer"
                  >
                    <td className="px-3 py-2.5 font-medium text-brand-primary-light">{c.name}</td>
                    <td className="px-3 py-2.5 text-xs text-gray-400">{c.billing_type}</td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {c.monthly_contract_value != null ? `$${c.monthly_contract_value.toLocaleString()}` : '-'}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">{c.hours_consumed}h</td>
                    <td className="px-3 py-2.5 tabular-nums">{c.ticket_count}</td>
                    <td className="px-3 py-2.5 tabular-nums text-gray-400">
                      ${c.service_cost.toLocaleString()}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {c.effective_hourly_rate != null ? (
                        <span className={clsx(
                          c.effective_hourly_rate >= techCost * 1.5 ? 'text-emerald-400' :
                          c.effective_hourly_rate >= techCost ? 'text-yellow-400' : 'text-red-400'
                        )}>
                          ${c.effective_hourly_rate}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {c.gross_margin != null ? (
                        <span className={clsx(c.gross_margin >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                          ${c.gross_margin.toLocaleString()}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {c.gross_margin_pct != null ? (
                        <span className={clsx(
                          'font-semibold',
                          c.gross_margin_pct >= 40 ? 'text-emerald-400' :
                          c.gross_margin_pct >= 20 ? 'text-yellow-400' : 'text-red-400'
                        )}>
                          {c.gross_margin_pct}%
                        </span>
                      ) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-500 text-right">
            Cost calculated at ${techCost}/hr. Set contract values in billing_config to see margin analysis.
          </p>
        </>
      )}
    </div>
  )
}
