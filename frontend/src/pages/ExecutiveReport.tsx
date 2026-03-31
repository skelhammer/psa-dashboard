import { useExecutiveReport, useExecutiveCharts, useExecutiveSummary } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import ChartCard from '../components/ChartCard'
import GlobalFilters from '../components/GlobalFilters'
import ExportButtons from '../components/ExportButtons'
import InsightCard from '../components/InsightCard'
import { exportMultiSectionCSV } from '../utils/export'
import clsx from 'clsx'
import { TrendingUp, TrendingDown, CircleCheck, AlertTriangle, CircleX } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, ComposedChart, ReferenceLine,
  Cell, Legend,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

interface ExecKpiProps {
  label: string
  value: string | number
  mom?: number | null
  yoy?: number | null
  direction?: 'up-good' | 'down-good'
  colorClass?: string
}

function ExecKpiCard({ label, value, mom, yoy, direction, colorClass }: ExecKpiProps) {
  const changeIndicator = (pct: number | null | undefined, prefix: string) => {
    if (pct == null || pct === 0) return <span className="text-gray-600">{prefix}: --</span>
    const isPositive = pct > 0
    let color = 'text-gray-500'
    if (direction === 'up-good') {
      color = isPositive ? 'text-emerald-400' : 'text-red-400'
    } else if (direction === 'down-good') {
      color = isPositive ? 'text-red-400' : 'text-emerald-400'
    }
    return (
      <span className={clsx('inline-flex items-center gap-1', color)}>
        {prefix}: {isPositive
          ? <TrendingUp size={11} strokeWidth={2.5} />
          : <TrendingDown size={11} strokeWidth={2.5} />
        } {isPositive ? '+' : ''}{pct}%
      </span>
    )
  }

  return (
    <div className={clsx(
      'group relative overflow-hidden rounded-xl border p-5 animate-fade-in transition-all duration-200',
      'bg-[#111113] shadow-lg shadow-black/25 hover:shadow-xl hover:-translate-y-0.5',
      colorClass || 'border-white/[0.08] hover:border-white/[0.15]',
    )}>
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-gradient-to-r from-transparent via-brand-primary/40 to-transparent" />
      <div className="absolute inset-0 bg-gradient-to-br from-brand-primary/[0.04] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
      <div className="relative">
        <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2.5">{label}</p>
        <p className="text-2xl font-bold tabular-nums tracking-tight text-white">{value}</p>
        <div className="flex flex-col gap-0.5 mt-2 text-[11px] font-medium tabular-nums">
          {changeIndicator(mom, 'MoM')}
          {changeIndicator(yoy, 'YoY')}
        </div>
      </div>
    </div>
  )
}

const utilColor = (pct: number) => {
  if (pct >= 60 && pct <= 85) return 'text-emerald-400'
  if (pct > 85 || pct < 40) return 'text-red-400'
  return 'text-yellow-400'
}

const slaColor = (pct: number) => {
  if (pct >= 95) return 'text-emerald-400'
  if (pct >= 80) return 'text-yellow-400'
  return 'text-red-400'
}

const healthIcons = {
  green: CircleCheck,
  yellow: AlertTriangle,
  red: CircleX,
}
const healthColors = {
  green: 'text-emerald-400 border-emerald-500/30 bg-emerald-500/5',
  yellow: 'text-yellow-400 border-yellow-500/30 bg-yellow-500/5',
  red: 'text-red-400 border-red-500/30 bg-red-500/5',
}

export default function ExecutiveReport() {
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data: report, isLoading } = useExecutiveReport(params)
  const { data: charts } = useExecutiveCharts(params)
  const { data: summary } = useExecutiveSummary()

  if (isLoading && !report) {
    return <div className="text-gray-500">Loading executive report...</div>
  }

  const kpis = report?.kpis
  const mom = report?.mom_change
  const yoy = report?.yoy_change

  const handleExportCSV = () => {
    const sections: { name: string; data: Record<string, any>[] }[] = []
    if (kpis) {
      sections.push({
        name: 'Executive KPI Summary',
        data: [{
          'Period': report?.period_label,
          'Tickets Created': kpis.tickets_created,
          'Tickets Closed': kpis.tickets_closed,
          'Open Backlog': kpis.open_backlog,
          'SLA Compliance %': kpis.sla_compliance_pct,
          'Avg First Response': kpis.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-',
          'Avg Resolution': kpis.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-',
          'Worklog Hours': kpis.total_worklog_hours,
          'Team Utilization %': kpis.team_utilization_pct,
          'Billing Compliance %': kpis.billing_compliance_pct,
          'Billing Flags': kpis.unresolved_billing_flags,
          'Reopened': kpis.reopened_count,
        }],
      })
    }
    if (charts?.volume_comparison?.length) sections.push({ name: 'Volume YoY Comparison', data: charts.volume_comparison })
    if (charts?.sla_trend?.length) sections.push({ name: 'SLA Compliance Trend', data: charts.sla_trend })
    if (charts?.backlog_trend?.length) sections.push({ name: 'Backlog Trajectory', data: charts.backlog_trend })
    if (charts?.team_summary?.length) sections.push({ name: 'Team Performance', data: charts.team_summary })
    if (charts?.top_clients?.length) sections.push({ name: 'Top Clients', data: charts.top_clients })
    if (charts?.billing_trend?.length) sections.push({ name: 'Billing Compliance Trend', data: charts.billing_trend })
    if (charts?.category_distribution?.length) sections.push({ name: 'Top Categories', data: charts.category_distribution })
    exportMultiSectionCSV(sections, 'executive_report')
  }

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Executive Report</h2>
          <p className="text-sm text-gray-500 mt-1">
            Service desk performance summary for {report?.period_label || '...'}
          </p>
        </div>
        <ExportButtons onCSV={handleExportCSV} pageTitle="Executive Report" />
      </div>
      <GlobalFilters />

      {/* CEO Summary */}
      {summary?.health && (() => {
        const h = summary.health
        const color = h.health as 'green' | 'yellow' | 'red'
        const HealthIcon = healthIcons[color] || CircleCheck
        return (
          <div className={clsx('rounded-xl border p-6 animate-fade-in', healthColors[color])}>
            <div className="flex items-start gap-4">
              <HealthIcon size={28} className="shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="text-base font-semibold text-gray-100">{h.summary}</p>
                <div className="flex flex-wrap gap-6 mt-3 text-sm">
                  <div>
                    <span className="text-gray-400">Open Backlog: </span>
                    <span className="font-bold text-white">{h.open_backlog}</span>
                    <span className="text-gray-500 text-xs ml-1">(clears in ~{h.clearance_days}d)</span>
                  </div>
                  <div>
                    <span className="text-gray-400">SLA: </span>
                    <span className="font-bold text-white">{h.sla_pct}%</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Close Trend: </span>
                    <span className={clsx('font-bold', h.close_change_pct >= 0 ? 'text-emerald-400' : 'text-red-400')}>
                      {h.close_change_pct >= 0 ? '+' : ''}{h.close_change_pct}% MoM
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Insight Cards */}
      {summary?.insights?.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {summary.insights.map((insight: any, i: number) => (
            <InsightCard key={i} type={insight.type} title={insight.title} description={insight.description} />
          ))}
        </div>
      )}

      {/* KPI Scoreboard */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <ExecKpiCard
          label="Tickets Created"
          value={kpis?.tickets_created ?? '-'}
          mom={mom?.tickets_created}
          yoy={yoy?.tickets_created}
          direction="down-good"
        />
        <ExecKpiCard
          label="Tickets Closed"
          value={kpis?.tickets_closed ?? '-'}
          mom={mom?.tickets_closed}
          yoy={yoy?.tickets_closed}
          direction="up-good"
        />
        <ExecKpiCard
          label="Open Backlog"
          value={kpis?.open_backlog ?? '-'}
          colorClass={
            (kpis?.open_backlog ?? 0) > 40 ? 'border-red-500/30' :
            (kpis?.open_backlog ?? 0) > 20 ? 'border-yellow-500/30' : 'border-white/[0.08]'
          }
        />
        <ExecKpiCard
          label="SLA Compliance"
          value={`${kpis?.sla_compliance_pct ?? '-'}%`}
          mom={mom?.sla_compliance_pct}
          yoy={yoy?.sla_compliance_pct}
          direction="up-good"
          colorClass={
            (kpis?.sla_compliance_pct ?? 100) >= 95 ? 'border-emerald-500/30' :
            (kpis?.sla_compliance_pct ?? 100) >= 80 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <ExecKpiCard
          label="Avg First Response"
          value={kpis?.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-'}
          mom={mom?.avg_first_response_minutes}
          yoy={yoy?.avg_first_response_minutes}
          direction="down-good"
        />
        <ExecKpiCard
          label="Avg Resolution"
          value={kpis?.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-'}
          mom={mom?.avg_resolution_minutes}
          yoy={yoy?.avg_resolution_minutes}
          direction="down-good"
        />
        <ExecKpiCard
          label="Worklog Hours"
          value={kpis?.total_worklog_hours ?? '-'}
          mom={mom?.total_worklog_hours}
          yoy={yoy?.total_worklog_hours}
          direction="up-good"
        />
        <ExecKpiCard
          label="Team Utilization"
          value={`${kpis?.team_utilization_pct ?? '-'}%`}
          colorClass={
            kpis?.team_utilization_pct != null ? (
              kpis.team_utilization_pct >= 60 && kpis.team_utilization_pct <= 85
                ? 'border-emerald-500/30'
                : kpis.team_utilization_pct > 85 ? 'border-red-500/30' : 'border-yellow-500/30'
            ) : 'border-white/[0.08]'
          }
        />
        <ExecKpiCard
          label="Billing Compliance"
          value={`${kpis?.billing_compliance_pct ?? '-'}%`}
          mom={mom?.billing_compliance_pct}
          yoy={yoy?.billing_compliance_pct}
          direction="up-good"
          colorClass={
            (kpis?.billing_compliance_pct ?? 100) >= 95 ? 'border-emerald-500/30' :
            (kpis?.billing_compliance_pct ?? 100) >= 80 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <ExecKpiCard
          label="Billing Flags"
          value={kpis?.unresolved_billing_flags ?? 0}
          colorClass={(kpis?.unresolved_billing_flags ?? 0) > 0 ? 'border-red-500/30' : 'border-white/[0.08]'}
        />
        <ExecKpiCard
          label="Reopened Tickets"
          value={kpis?.reopened_count ?? 0}
          mom={mom?.reopened_count}
          yoy={yoy?.reopened_count}
          direction="down-good"
          colorClass={(kpis?.reopened_count ?? 0) > 3 ? 'border-yellow-500/30' : 'border-white/[0.08]'}
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Ticket Volume: Year over Year" exportData={charts?.volume_comparison} exportFilename="volume_yoy">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={charts?.volume_comparison || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Legend
                wrapperStyle={{ fontSize: 11, color: '#9ca3af' }}
                formatter={(val: string) => val === 'current_year' ? 'This Year' : 'Last Year'}
              />
              <Bar dataKey="current_year" fill={BRAND.primary} radius={[2, 2, 0, 0]} name="current_year" />
              <Bar dataKey="prior_year" fill="#4B5563" radius={[2, 2, 0, 0]} name="prior_year" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="SLA Compliance Trend" exportData={charts?.sla_trend} exportFilename="sla_trend">
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={charts?.sla_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis domain={['dataMin - 5', 100]} tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip {...tooltipStyle} formatter={(v: number) => `${v}%`} />
              <ReferenceLine y={95} stroke="#34D399" strokeDasharray="3 3" label={{ value: "95% Target", fill: "#34D399", fontSize: 10, position: "insideTopRight" }} />
              <Line type="monotone" dataKey="compliance_pct" stroke={BRAND.primary} strokeWidth={2} dot={{ fill: BRAND.primary, r: 3 }} name="SLA %" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Backlog Trend" exportData={charts?.backlog_trend} exportFilename="backlog_trend">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={charts?.backlog_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
              <Bar dataKey="opened" fill="#60A5FA" radius={[2, 2, 0, 0]} name="Opened" />
              <Bar dataKey="closed" fill="#34D399" radius={[2, 2, 0, 0]} name="Closed" />
              <Line type="monotone" dataKey="open_count" stroke="#F87171" strokeWidth={2} dot={false} name="Open Backlog" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Resolution Time Distribution" exportData={charts?.resolution_distribution} exportFilename="resolution_dist">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={charts?.resolution_distribution || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="bucket" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(charts?.resolution_distribution || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Team Performance Table */}
      <ChartCard title="Team Performance Summary" exportData={charts?.team_summary} exportFilename="team_performance">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-gray-500 border-b border-white/[0.08]">
                <th className="pb-3 pr-4">Technician</th>
                <th className="pb-3 pr-4 text-right">Open</th>
                <th className="pb-3 pr-4 text-right">Closed</th>
                <th className="pb-3 pr-4 text-right">SLA %</th>
                <th className="pb-3 pr-4 text-right">Utilization</th>
                <th className="pb-3 pr-4 text-right">Avg Resolution</th>
                <th className="pb-3 text-right">Hours Logged</th>
              </tr>
            </thead>
            <tbody>
              {(charts?.team_summary || []).map((tech: any) => (
                <tr key={tech.name} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="py-3 pr-4 font-medium text-gray-200">{tech.name}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-gray-400">{tech.open_tickets}</td>
                  <td className="py-3 pr-4 text-right tabular-nums font-semibold">{tech.closed}</td>
                  <td className={clsx('py-3 pr-4 text-right tabular-nums font-semibold', slaColor(tech.sla_pct))}>
                    {tech.sla_pct}%
                  </td>
                  <td className={clsx('py-3 pr-4 text-right tabular-nums font-semibold', utilColor(tech.utilization_pct))}>
                    {tech.utilization_pct}%
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums text-gray-400">
                    {tech.avg_resolution_minutes ? formatDuration(tech.avg_resolution_minutes) : '-'}
                  </td>
                  <td className="py-3 text-right tabular-nums text-gray-400">{tech.worklog_hours}h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      {/* Charts Row 3 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Top Clients by Volume" exportData={charts?.top_clients} exportFilename="top_clients">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={charts?.top_clients || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={140} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="volume" radius={[0, 4, 4, 0]}>
                {(charts?.top_clients || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Billing Compliance Trend" exportData={charts?.billing_trend} exportFilename="billing_trend">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={charts?.billing_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis domain={['dataMin - 5', 100]} tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip {...tooltipStyle} formatter={(v: number) => `${v}%`} />
              <ReferenceLine y={95} stroke="#34D399" strokeDasharray="3 3" label={{ value: "95% Target", fill: "#34D399", fontSize: 10, position: "insideTopRight" }} />
              <Line type="monotone" dataKey="compliance_pct" stroke="#F59E0B" strokeWidth={2} dot={{ fill: '#F59E0B', r: 3 }} name="Billing %" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Top Categories */}
      <ChartCard title="Top Categories" exportData={charts?.category_distribution} exportFilename="category_distribution">
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={charts?.category_distribution || []} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
            <YAxis dataKey="category" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={120} />
            <Tooltip {...tooltipStyle} />
            <Bar dataKey="count" fill={BRAND.primary} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Footer */}
      <div className="text-center text-[11px] text-gray-600 py-4 border-t border-white/[0.04]">
        Report generated {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString()}
      </div>
    </div>
  )
}
