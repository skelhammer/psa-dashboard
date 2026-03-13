import { useNavigate } from 'react-router-dom'
import { useOverview, useOverviewCharts } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'
import GlobalFilters from '../components/GlobalFilters'
import ExportButtons from '../components/ExportButtons'
import { exportMultiSectionCSV } from '../utils/export'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, PieChart, Pie, Cell,
  ReferenceLine,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

export default function Overview() {
  const navigate = useNavigate()
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useOverview(params)
  const { data: charts } = useOverviewCharts(params)

  if (isLoading) {
    return <div className="text-gray-500">Loading overview...</div>
  }

  const kpis = data?.kpis
  const pct = data?.pct_change
  const periodLabel = data?.date_range_label

  const handleExportCSV = () => {
    const sections: { name: string; data: Record<string, any>[] }[] = []

    if (kpis) {
      sections.push({
        name: 'KPI Summary',
        data: [{
          'Open Tickets': kpis.total_open,
          'Created Today': kpis.created_today,
          'Closed Today': kpis.closed_today,
          'Created This Week': kpis.created_this_week,
          'Closed This Week': kpis.closed_this_week,
          'Created (Period)': kpis.created_period,
          'Closed (Period)': kpis.closed_period,
          'Avg First Response': kpis.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-',
          'Avg Resolution': kpis.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-',
          'SLA Compliance %': kpis.sla_compliance_pct,
          'Worklog Hours': kpis.total_worklog_hours,
          'Billing Flags': kpis.unresolved_billing_flags,
          'Reopened': kpis.reopened_period,
        }],
      })
    }
    if (charts?.volume_trend?.length) sections.push({ name: 'Volume Trend', data: charts.volume_trend })
    if (charts?.aging_buckets?.length) sections.push({ name: 'Ticket Aging', data: charts.aging_buckets })
    if (charts?.workload_balance?.length) sections.push({ name: 'Workload Balance', data: charts.workload_balance })
    if (charts?.group_distribution?.length) sections.push({ name: 'Open Tickets by Group', data: charts.group_distribution })
    if (charts?.status_distribution?.length) sections.push({ name: 'Tickets by Status', data: charts.status_distribution })
    if (charts?.priority_distribution?.length) sections.push({ name: 'Tickets by Priority', data: charts.priority_distribution })
    if (charts?.sla_trend?.length) sections.push({ name: 'SLA Compliance Trend', data: charts.sla_trend })

    exportMultiSectionCSV(sections, 'overview_report')
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="flex items-center justify-between page-header">
        <div>
          <h2 className="text-xl font-bold">Overview</h2>
          <p className="text-sm text-gray-500 mt-1">
            KPIs, volume trends, backlog tracking, and workload balance at a glance.
          </p>
        </div>
        <ExportButtons
          onCSV={handleExportCSV}
          pageTitle="Overview"
        />
      </div>

      <GlobalFilters />

      {/* KPI Cards - Row 1: Current snapshot */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Open Tickets" value={kpis?.total_open ?? '-'} onClick={() => navigate('/manage-to-zero')} />
        <KpiCard
          label="Created / Closed Today"
          value={`${kpis?.created_today ?? 0} / ${kpis?.closed_today ?? 0}`}
          colorClass={
            (kpis?.closed_today ?? 0) >= (kpis?.created_today ?? 0)
              ? 'border-green-500/30' : 'border-red-500/30'
          }
          onClick={() => navigate('/work-queue')}
        />
        <KpiCard
          label="Created / Closed This Week"
          value={`${kpis?.created_this_week ?? 0} / ${kpis?.closed_this_week ?? 0}`}
          colorClass={
            (kpis?.closed_this_week ?? 0) >= (kpis?.created_this_week ?? 0)
              ? 'border-green-500/30' : 'border-red-500/30'
          }
          onClick={() => navigate('/manage-to-zero')}
        />
        <KpiCard
          label="Billing Flags"
          value={kpis?.unresolved_billing_flags ?? 0}
          colorClass={kpis?.unresolved_billing_flags > 0 ? 'border-red-500/30' : ''}
          onClick={() => navigate('/billing')}
        />
      </div>

      {/* KPI Cards - Row 2: Period metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard label="Created (Period)" value={kpis?.created_period ?? '-'} subtitle={periodLabel} pctChange={pct?.created_period} changeDirection="up-good" />
        <KpiCard
          label="Closed (Period)"
          value={kpis?.closed_period ?? '-'}
          subtitle={periodLabel}
          pctChange={pct?.closed_period}
          changeDirection="up-good"
        />
        <KpiCard
          label="Avg First Response"
          value={kpis?.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-'}
          subtitle={periodLabel}
          pctChange={pct?.avg_first_response_minutes}
          changeDirection="down-good"
          onClick={() => navigate('/technicians')}
        />
        <KpiCard
          label="Avg Resolution"
          value={kpis?.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-'}
          subtitle={periodLabel}
          pctChange={pct?.avg_resolution_minutes}
          changeDirection="down-good"
          onClick={() => navigate('/technicians')}
        />
        <KpiCard
          label="SLA Compliance"
          value={`${kpis?.sla_compliance_pct ?? '-'}%`}
          subtitle={periodLabel}
          colorClass={
            (kpis?.sla_compliance_pct ?? 100) >= 95 ? 'border-green-500/30' :
            (kpis?.sla_compliance_pct ?? 100) >= 80 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
          pctChange={pct?.sla_compliance_pct}
          changeDirection="up-good"
          onClick={() => navigate('/technicians')}
        />
        <KpiCard
          label="Worklog Hours"
          value={kpis?.total_worklog_hours ?? '-'}
          subtitle={periodLabel}
          pctChange={pct?.total_worklog_hours}
          changeDirection="up-good"
          onClick={() => navigate('/technicians')}
        />
        <KpiCard
          label="Reopened"
          value={kpis?.reopened_period ?? 0}
          subtitle={periodLabel}
          pctChange={pct?.reopened_period}
          changeDirection="down-good"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Volume Trend */}
        <ChartCard title="Ticket Volume" exportData={charts?.volume_trend} exportFilename="volume_trend">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.volume_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill={BRAND.primary} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Aging Buckets */}
        <ChartCard title="Ticket Aging (Open Tickets)" exportData={charts?.aging_buckets} exportFilename="ticket_aging">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.aging_buckets || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="bucket" type="category" tick={{ fontSize: 10, fill: '#6b7280' }} width={50} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill={BRAND.primary} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Workload Balance */}
        <ChartCard title="Workload Balance" exportData={charts?.workload_balance} exportFilename="workload_balance">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.workload_balance || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="technician" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={100} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {(charts?.workload_balance || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Group Distribution */}
        <ChartCard title="Open Tickets by Group" exportData={charts?.group_distribution} exportFilename="group_distribution">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.group_distribution || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="group" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={110} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {(charts?.group_distribution || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Status Distribution */}
        <ChartCard title="Tickets by Status" exportData={charts?.status_distribution} exportFilename="status_distribution">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={charts?.status_distribution || []}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={80}
                innerRadius={45}
                paddingAngle={2}
                label={({ cx, cy, midAngle, outerRadius, name, percent }: any) => {
                  const RADIAN = Math.PI / 180
                  const radius = outerRadius + 28
                  const x = cx + radius * Math.cos(-midAngle * RADIAN)
                  const y = cy + radius * Math.sin(-midAngle * RADIAN)
                  return (
                    <text x={x} y={y} fill="#9ca3af" fontSize={11} textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central">
                      {name} ({(percent * 100).toFixed(0)}%)
                    </text>
                  )
                }}
                labelLine={{ stroke: '#4b5563', strokeWidth: 1 }}
              >
                {(charts?.status_distribution || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Priority Distribution */}
        <ChartCard title="Tickets by Priority" exportData={charts?.priority_distribution} exportFilename="priority_distribution">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.priority_distribution || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="priority" tick={{ fontSize: 11, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {(charts?.priority_distribution || []).map((entry: any, i: number) => {
                  const colors: Record<string, string> = {
                    Critical: '#f87171', Urgent: '#f87171', High: '#fb923c',
                    Medium: '#fbbf24', Low: '#60a5fa', 'Very Low': '#9ca3af',
                  }
                  return <Cell key={i} fill={colors[entry.priority] || BRAND.primary} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* SLA Compliance Trend */}
        <ChartCard title="SLA Compliance Trend" exportData={charts?.sla_trend} exportFilename="sla_trend">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={charts?.sla_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis domain={['dataMin - 5', 100]} tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip {...tooltipStyle} />
              <ReferenceLine y={95} stroke="#34D399" strokeDasharray="3 3" label={{ value: "95% Target", fill: "#34D399", fontSize: 10 }} />
              <Line type="monotone" dataKey="compliance_pct" stroke={BRAND.primary} strokeWidth={2} dot={{ fill: BRAND.primary }} name="SLA %" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

      </div>
    </div>
  )
}
