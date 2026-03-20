import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTechnicians, useTeams, useUpdateTechRole } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import GlobalFilters from '../components/GlobalFilters'
import ExportButtons from '../components/ExportButtons'
import { Trophy } from 'lucide-react'
import clsx from 'clsx'

const DASHBOARD_ROLES = ['technician', 'administration', 'executive', 'sales'] as const
const ROLE_COLORS: Record<string, string> = {
  technician: 'text-blue-400 bg-blue-400/10 border-blue-400/30',
  administration: 'text-purple-400 bg-purple-400/10 border-purple-400/30',
  executive: 'text-amber-400 bg-amber-400/10 border-amber-400/30',
  sales: 'text-cyan-400 bg-cyan-400/10 border-cyan-400/30',
}

function RolePicker({ roles, onChange }: { roles: string[]; onChange: (roles: string[]) => void }) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  const toggle = (role: string) => {
    const current = new Set(roles)
    if (current.has(role)) {
      if (current.size > 1) current.delete(role)
    } else {
      current.add(role)
    }
    onChange(Array.from(current))
  }

  const handleOpen = () => {
    if (btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect()
      setPos({ top: rect.bottom + 4, left: rect.left })
    }
    setOpen(!open)
  }

  return (
    <>
      <button
        ref={btnRef}
        onClick={handleOpen}
        className="flex flex-wrap gap-1"
      >
        {roles.map(r => (
          <span
            key={r}
            className={clsx(
              'px-1.5 py-0 rounded-full text-[10px] font-bold border',
              ROLE_COLORS[r] || ROLE_COLORS.technician,
            )}
          >
            {r}
          </span>
        ))}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="fixed z-50 bg-[#1a1a1e] border border-white/[0.12] rounded-lg shadow-xl py-1 min-w-[160px]"
            style={{ top: pos.top, left: pos.left }}
          >
            {DASHBOARD_ROLES.map(r => (
              <label
                key={r}
                className="flex items-center gap-2 px-3 py-1.5 hover:bg-white/[0.05] cursor-pointer text-xs"
              >
                <input
                  type="checkbox"
                  checked={roles.includes(r)}
                  onChange={() => toggle(r)}
                  className="accent-blue-500 rounded"
                />
                <span className={clsx('font-medium', ROLE_COLORS[r]?.split(' ')[0] || 'text-gray-300')}>
                  {r}
                </span>
              </label>
            ))}
          </div>
        </>
      )}
    </>
  )
}

function utilizationColor(pct: number): string {
  if (pct >= 60 && pct <= 80) return 'text-green-400'
  if ((pct >= 80 && pct <= 90) || pct < 40) return 'text-yellow-400'
  if (pct > 90) return 'text-red-400'
  return 'text-gray-400'
}

type LeaderboardMetric = 'productivity' | 'response' | 'resolution' | 'sla' | 'hours'

function rankLabel(rank: number): string {
  if (rank === 1) return '1st'
  if (rank === 2) return '2nd'
  if (rank === 3) return '3rd'
  return `${rank}th`
}

const PODIUM = {
  1: { color: '#FFD700', bg: 'rgba(255, 215, 0, 0.08)', border: 'rgba(255, 215, 0, 0.3)', glow: 'rgba(255, 215, 0, 0.05)', label: 'Gold' },
  2: { color: '#A8B4C4', bg: 'rgba(168, 180, 196, 0.10)', border: 'rgba(168, 180, 196, 0.35)', glow: 'rgba(168, 180, 196, 0.08)', label: 'Silver' },
  3: { color: '#CD7F32', bg: 'rgba(205, 127, 50, 0.08)', border: 'rgba(205, 127, 50, 0.3)', glow: 'rgba(205, 127, 50, 0.05)', label: 'Bronze' },
} as Record<number, { color: string; bg: string; border: string; glow: string; label: string }>

function rankColor(rank: number): string {
  return PODIUM[rank]?.color || '#6b7280'
}

function sortTechs(techs: any[], metric: LeaderboardMetric): any[] {
  let filtered: any[]
  switch (metric) {
    case 'productivity':
      filtered = techs.filter(t => t.closed_period > 0 || t.worklog_hours > 0)
      return filtered.sort((a, b) => b.closed_period - a.closed_period)
    case 'response':
      filtered = techs.filter(t => t.avg_first_response_minutes > 0)
      return filtered.sort((a, b) => a.avg_first_response_minutes - b.avg_first_response_minutes)
    case 'resolution':
      filtered = techs.filter(t => t.avg_resolution_minutes > 0)
      return filtered.sort((a, b) => a.avg_resolution_minutes - b.avg_resolution_minutes)
    case 'sla':
      filtered = techs.filter(t => t.closed_period > 0 || t.open_tickets > 0)
      return filtered.sort((a, b) =>
        (a.fr_violation_pct + a.res_violation_pct) - (b.fr_violation_pct + b.res_violation_pct)
      )
    case 'hours':
      filtered = techs.filter(t => t.worklog_hours > 0)
      return filtered.sort((a, b) => b.worklog_hours - a.worklog_hours)
  }
}

function primaryValue(tech: any, metric: LeaderboardMetric): string {
  switch (metric) {
    case 'productivity':
      return `${tech.closed_period} closed`
    case 'response':
      return formatDuration(tech.avg_first_response_minutes)
    case 'resolution':
      return formatDuration(tech.avg_resolution_minutes)
    case 'sla':
      return `${Math.max(0, 100 - tech.fr_violation_pct - tech.res_violation_pct).toFixed(1)}% compliant`
    case 'hours':
      return `${tech.worklog_hours}h logged`
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
    case 'resolution':
      return [
        formatDuration(tech.avg_first_response_minutes) + ' avg FR',
        tech.closed_period + ' closed',
      ]
    case 'sla':
      return [
        `FR violations: ${tech.fr_violations} (${tech.fr_violation_pct}%)`,
        `Res violations: ${tech.res_violations} (${tech.res_violation_pct}%)`,
      ]
    case 'hours':
      return [
        tech.utilization_pct + '% utilization',
        tech.closed_period + ' closed',
        tech.open_tickets + ' open',
      ]
  }
}

export default function Technicians() {
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useTechnicians(params)
  const { data: teamsData } = useTeams(params)
  const updateRole = useUpdateTechRole()
  const navigate = useNavigate()
  const [viewMode, setViewMode] = useState<'table' | 'leaderboard' | 'teams'>('table')
  const [leaderboardMetric, setLeaderboardMetric] = useState<LeaderboardMetric>('productivity')
  const [sortCol, setSortCol] = useState<string>('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  const techs = data?.technicians || []
  const teams = teamsData?.teams || []
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

  const columns = [
    { key: 'name', label: 'Name', type: 'string' },
    { key: 'dashboard_role', label: 'Role', type: 'string' },
    { key: 'open_tickets', label: 'Open', type: 'number' },
    { key: 'closed_period', label: 'Closed', type: 'number' },
    { key: 'avg_first_response_minutes', label: 'Avg FR', type: 'number' },
    { key: 'avg_resolution_minutes', label: 'Avg Res', type: 'number' },
    { key: 'fr_violation_pct', label: 'FR Viol', type: 'number' },
    { key: 'res_violation_pct', label: 'Res Viol', type: 'number' },
    { key: 'worklog_hours', label: 'Hours', type: 'number' },
    { key: 'utilization_pct', label: 'Util %', type: 'number' },
    { key: 'stale_tickets', label: 'Stale', type: 'number' },
    { key: 'reopened_tickets', label: 'Reopened', type: 'number' },
    { key: 'billing_compliance_pct', label: 'Billing %', type: 'number' },
  ]

  const sortedTableTechs = [...techs].sort((a: any, b: any) => {
    const aVal = a[sortCol]
    const bVal = b[sortCol]
    const cmp = typeof aVal === 'string' ? aVal.localeCompare(bVal) : aVal - bVal
    return sortDir === 'asc' ? cmp : -cmp
  })

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Technician Performance</h2>
          <p className="text-sm text-gray-500 mt-1">
            Per-tech metrics including response times, worklog hours, utilization, and SLA compliance.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-[#111113] rounded-lg p-1 border border-white/[0.08]">
            <button
              onClick={() => setViewMode('table')}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-md transition-colors',
                viewMode === 'table'
                  ? 'bg-brand-primary/20 text-brand-primary-light font-medium'
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
                  ? 'bg-brand-primary/20 text-brand-primary-light font-medium'
                  : 'text-gray-400 hover:text-gray-200'
              )}
            >
              Leaderboard
            </button>
            <button
              onClick={() => setViewMode('teams')}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-md transition-colors',
                viewMode === 'teams'
                  ? 'bg-brand-primary/20 text-brand-primary-light font-medium'
                  : 'text-gray-400 hover:text-gray-200'
              )}
            >
              Teams
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
          {(['productivity', 'response', 'resolution', 'sla', 'hours'] as LeaderboardMetric[]).map((m) => {
            const labels: Record<LeaderboardMetric, string> = {
              productivity: 'Productivity',
              response: 'Response Time',
              resolution: 'Resolution Time',
              sla: 'SLA Compliance',
              hours: 'Hours Billed',
            }
            return (
            <button
              key={m}
              onClick={() => setLeaderboardMetric(m)}
              className={clsx(
                'px-3 py-1.5 text-sm rounded-lg border transition-colors',
                leaderboardMetric === m
                  ? 'border-brand-primary/50 bg-brand-primary/10 text-brand-primary-light'
                  : 'border-zinc-700 text-gray-400 hover:text-gray-200 hover:border-zinc-600'
              )}
            >
              {labels[m]}
            </button>
            )
          })}
        </div>
      )}

      {viewMode === 'table' && (
        <div className="overflow-x-auto rounded-xl border border-white/[0.08] shadow-lg shadow-black/20">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#111113] border-b border-white/[0.08]">
                {columns.map(col => (
                  <th
                    key={col.key}
                    onClick={() => {
                      if (sortCol === col.key) {
                        setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
                      } else {
                        setSortCol(col.key)
                        setSortDir(col.type === 'string' ? 'asc' : 'desc')
                      }
                    }}
                    className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap cursor-pointer hover:text-gray-300 select-none"
                  >
                    {col.label}
                    {sortCol === col.key && (
                      <span className="ml-1">{sortDir === 'asc' ? '\u25B2' : '\u25BC'}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {sortedTableTechs.map((tech: any) => (
                <tr
                  key={tech.id}
                  className="hover:bg-zinc-800/30 transition-colors cursor-pointer"
                >
                  <td className="px-3 py-2.5 font-medium text-brand-primary-light" onClick={() => navigate(`/technicians/${tech.id}`)}>{tech.name}</td>
                  <td className="px-3 py-2.5" onClick={e => e.stopPropagation()}>
                    <RolePicker
                      roles={(tech.dashboard_role || 'technician').split(',').map((r: string) => r.trim())}
                      onChange={roles => updateRole.mutate({ techId: tech.id, dashboard_roles: roles })}
                    />
                  </td>
                  <td className="px-3 py-2.5 tabular-nums" onClick={() => navigate(`/technicians/${tech.id}`)}>{tech.open_tickets}</td>
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
      )}

      {viewMode === 'leaderboard' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedTechs.map((tech: any, idx: number) => {
            const rank = idx + 1
            const podium = PODIUM[rank]
            const color = rankColor(rank)
            return (
              <div
                key={tech.id}
                onClick={() => navigate(`/technicians/${tech.id}`)}
                className="card card-hover relative overflow-hidden"
                style={{
                  borderColor: podium?.border || undefined,
                  backgroundColor: podium?.bg || undefined,
                  boxShadow: podium ? `0 0 24px ${podium.glow}` : undefined,
                }}
              >
                {podium && (
                  <div
                    className="absolute top-0 right-0 w-24 h-24 opacity-[0.04] pointer-events-none"
                    style={{ color: podium.color }}
                  >
                    <Trophy className="w-full h-full" />
                  </div>
                )}
                <div className="relative flex items-start gap-3">
                  <div className="flex-shrink-0 flex flex-col items-center gap-1">
                    {podium ? (
                      <div
                        className="w-10 h-10 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: `${podium.color}20`, color: podium.color }}
                      >
                        <Trophy size={20} />
                      </div>
                    ) : (
                      <div
                        className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold bg-zinc-800/60 text-gray-500"
                      >
                        {rankLabel(rank)}
                      </div>
                    )}
                    {podium && (
                      <span className="text-[10px] font-bold tracking-wide uppercase" style={{ color: podium.color }}>
                        {podium.label}
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-brand-primary-light truncate">{tech.name}</p>
                    <p className="text-xl font-bold mt-1" style={{ color: podium ? color : undefined }}>
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

      {viewMode === 'teams' && (
        <div className="overflow-x-auto rounded-xl border border-white/[0.08] shadow-lg shadow-black/20">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[#111113] border-b border-white/[0.08]">
                {['Team', 'Members', 'Open', 'Created', 'Closed', 'SLA %', 'Avg Resolution', 'Hours'].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {teams.map((team: any) => (
                <tr key={team.team} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-brand-primary-light">{team.team}</td>
                  <td className="px-3 py-2.5 tabular-nums">{team.member_count}</td>
                  <td className="px-3 py-2.5 tabular-nums">{team.open_tickets}</td>
                  <td className="px-3 py-2.5 tabular-nums">{team.created_period}</td>
                  <td className="px-3 py-2.5 tabular-nums">{team.closed_period}</td>
                  <td className="px-3 py-2.5 tabular-nums">
                    <span className={clsx(
                      team.sla_compliance_pct >= 95 ? 'text-green-400' :
                      team.sla_compliance_pct >= 80 ? 'text-yellow-400' : 'text-red-400'
                    )}>
                      {team.sla_compliance_pct}%
                    </span>
                  </td>
                  <td className="px-3 py-2.5 tabular-nums text-xs">{formatDuration(team.avg_resolution_minutes)}</td>
                  <td className="px-3 py-2.5 tabular-nums">{team.worklog_hours}h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {periodLabel && (
        <p className="text-xs text-gray-500 text-right">{periodLabel}</p>
      )}
    </div>
  )
}
