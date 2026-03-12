import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTechnicians } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import GlobalFilters from '../components/GlobalFilters'
import ExportButtons from '../components/ExportButtons'
import clsx from 'clsx'

function utilizationColor(pct: number): string {
  if (pct >= 60 && pct <= 80) return 'text-green-400'
  if ((pct >= 80 && pct <= 90) || pct < 40) return 'text-yellow-400'
  if (pct > 90) return 'text-red-400'
  return 'text-gray-400'
}

type LeaderboardMetric = 'productivity' | 'response' | 'sla'

function rankLabel(rank: number): string {
  if (rank === 1) return '1st'
  if (rank === 2) return '2nd'
  if (rank === 3) return '3rd'
  return `${rank}th`
}

function rankColor(rank: number): string {
  if (rank === 1) return '#B49B7F'
  if (rank === 2) return '#C0C0C0'
  if (rank === 3) return '#CD7F32'
  return '#6b7280'
}

function sortTechs(techs: any[], metric: LeaderboardMetric): any[] {
  const sorted = [...techs]
  switch (metric) {
    case 'productivity':
      return sorted.sort((a, b) => b.closed_period - a.closed_period)
    case 'response':
      return sorted.sort((a, b) => a.avg_first_response_minutes - b.avg_first_response_minutes)
    case 'sla':
      return sorted.sort((a, b) =>
        (a.fr_violation_pct + a.res_violation_pct) - (b.fr_violation_pct + b.res_violation_pct)
      )
  }
}

function primaryValue(tech: any, metric: LeaderboardMetric): string {
  switch (metric) {
    case 'productivity':
      return `${tech.closed_period} closed`
    case 'response':
      return formatDuration(tech.avg_first_response_minutes)
    case 'sla':
      return `${Math.max(0, 100 - tech.fr_violation_pct - tech.res_violation_pct).toFixed(1)}% compliant`
  }
}

function secondaryStats(tech: any, metric: LeaderboardMetric): string[] {
  switch (metric) {
    case 'productivity':
      return [
        `${tech.open_tickets} open`,
        `${tech.worklog_hours}h logged`,
        `${tech.utilization_pct}% util`,
      ]
    case 'response':
      return [
        `Avg resolution: ${formatDuration(tech.avg_resolution_minutes)}`,
        `${tech.closed_period} closed`,
      ]
    case 'sla':
      return [
        `FR violations: ${tech.fr_violations} (${tech.fr_violation_pct}%)`,
        `Res violations: ${tech.res_violations} (${tech.res_violation_pct}%)`,
      ]
  }
}

export default function Technicians() {
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useTechnicians(params)
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<'table' | 'leaderboard'>('table')
  const [leaderboardMetric, setLeaderboardMetric] = useState<LeaderboardMetric>('productivity')

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  const techs = data?.technicians || []
  const periodLabel = data?.date_range_label || ''

  const techCsvData = techs.map((t: any) => ({
    name: t.name,
    open_tickets: t.open_tickets,
    closed_period: t.closed_period,
    avg_first_response: formatDuration(t.avg_first_response_minutes),
    avg_resolution: formatDuration(t.avg_resolution_minutes),
    fr_violations: `${t.fr_violations} (${t.fr_violation_pct}%)`,
    res_violations: `${t.res_violations} (${t.res_violation_pct}%)`,
    worklog_hours: t.worklog_hours,
    utilization_pct: t.utilization_pct,
    stale_tickets: t.stale_tickets,
    reopened_tickets: t.reopened_tickets,
    billing_compliance_pct: t.billing_compliance_pct,
  }))

  const techCsvColumns = [
    { key: 'name', label: 'Name' },
    { key: 'open_tickets', label: 'Open' },
    { key: 'closed_period', label: 'Closed' },
    { key: 'avg_first_response', label: 'Avg FR' },
    { key: 'avg_resolution', label: 'Avg Res' },
    { key: 'fr_violations', label: 'FR Viol' },
    { key: 'res_violations', label: 'Res Viol' },
    { key: 'worklog_hours', label: 'Hours' },
    { key: 'utilization_pct', label: 'Util %' },
    { key: 'stale_tickets', label: 'Stale' },
    { key: 'reopened_tickets', label: 'Reopened' },
    { key: 'billing_compliance_pct', label: 'Billing %' },
  ]

  const sortedTechs = sortTechs(techs, leaderboardMetric)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Technician Performance</h2>
          <p className="text-sm text-gray-500 mt-1">
            Per-tech metrics including response times, worklog hours, utilization, and SLA compliance.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-gray-900 rounded-lg p-1 border border-gray-800">
            <button
              onClick={() => setViewMode('table')}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-md transition-colors',
                viewMode === 'table'
                  ? 'bg-brand-gold/20 text-brand-gold font-medium'
                  : 'text-gray-400 hover:text-gray-200'
              )}
            >
              Table
            </button>
            <button
              onClick={() => setViewMode('leaderboard')}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-md transition-colors',
                viewMode === 'leaderboard'
                  ? 'bg-brand-gold/20 text-brand-gold font-medium'
                  : 'text-gray-400 hover:text-gray-200'
              )}
            >
              Leaderboard
            </button>
          </div>
          <ExportButtons
            csvData={techCsvData}
            csvFilename="technician_performance"
            csvColumns={techCsvColumns}
            pageTitle="Technician Performance"
          />
        </div>
      </div>

      <GlobalFilters />

      {viewMode === 'leaderboard' && (
        <div className="flex items-center gap-2">
          {(['productivity', 'response', 'sla'] as LeaderboardMetric[]).map((m) => (
            <button
              key={m}
              onClick={() => setLeaderboardMetric(m)}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-lg border transition-colors',
                leaderboardMetric === m
                  ? 'border-brand-gold/50 bg-brand-gold/10 text-brand-gold'
                  : 'border-gray-700 text-gray-400 hover:text-gray-200 hover:border-gray-600'
              )}
            >
              {m === 'productivity' ? 'Productivity' : m === 'response' ? 'Response Time' : 'SLA Compliance'}
            </button>
          ))}
        </div>
      )}

      {viewMode === 'table' ? (
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
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedTechs.map((tech: any, idx: number) => {
            const rank = idx + 1
            const color = rankColor(rank)
            return (
              <div
                key={tech.id}
                onClick={() => navigate(`/technicians/${tech.id}`)}
                className="card card-hover relative overflow-hidden"
                style={{ borderColor: rank <= 3 ? `${color}40` : undefined }}
              >
                <div className="flex items-start gap-3">
                  <div
                    className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold"
                    style={{ backgroundColor: `${color}20`, color }}
                  >
                    {rankLabel(rank)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-brand-gold truncate">{tech.name}</p>
                    <p className="text-xl font-bold mt-1" style={{ color: rank <= 3 ? color : undefined }}>
                      {primaryValue(tech, leaderboardMetric)}
                    </p>
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-2">
                      {secondaryStats(tech, leaderboardMetric).map((stat, i) => (
                        <span key={i} className="text-xs text-gray-500">{stat}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {periodLabel && (
        <p className="text-xs text-gray-500 text-right">{periodLabel}</p>
      )}
    </div>
  )
}
