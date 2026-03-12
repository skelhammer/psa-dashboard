import { useOverview, useOverviewCharts } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'
import GlobalFilters from '../components/GlobalFilters'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, PieChart, Pie, Cell, Legend,
  ComposedChart, Area,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px' },
  labelStyle: { color: '#9ca3af' },
}

export default function Overview() {
  const { toParams } = useFilterContext()
  const { data, isLoading } = useOverview(toParams())
  const { data: charts } = useOverviewCharts()

  if (isLoading) {
    return <div className="text-gray-500">Loading overview...</div>
  }

  const kpis = data?.kpis

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Overview</h2>
        <GlobalFilters />
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
        <KpiCard label="Open Tickets" value={kpis?.total_open ?? '-'} />
        <KpiCard label="Created Today" value={kpis?.created_today ?? '-'} />
        <KpiCard label="Created This Week" value={kpis?.created_this_week ?? '-'} />
        <KpiCard label="Created This Month" value={kpis?.created_this_month ?? '-'} />
        <KpiCard
          label="Open vs Closed (Week)"
          value={`${kpis?.open_vs_closed_ratio?.opened ?? 0} / ${kpis?.open_vs_closed_ratio?.closed ?? 0}`}
          colorClass={
            kpis?.open_vs_closed_ratio?.closed >= kpis?.open_vs_closed_ratio?.opened
              ? 'border-green-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Avg First Response"
          value={kpis?.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-'}
          subtitle="This month"
        />
        <KpiCard
          label="Avg Resolution"
          value={kpis?.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-'}
          subtitle="This month"
        />
        <KpiCard
          label="SLA Compliance"
          value={`${kpis?.sla_compliance_pct ?? '-'}%`}
          subtitle="This month"
          colorClass={
            (kpis?.sla_compliance_pct ?? 100) >= 95 ? 'border-green-500/30' :
            (kpis?.sla_compliance_pct ?? 100) >= 80 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="FCR Rate"
          value={`${kpis?.fcr_rate_pct ?? '-'}%`}
          subtitle="First contact resolution"
        />
        <KpiCard
          label="Worklog Hours"
          value={kpis?.total_worklog_hours ?? '-'}
          subtitle="This month"
        />
        <KpiCard
          label="Billing Flags"
          value={kpis?.unresolved_billing_flags ?? 0}
          colorClass={kpis?.unresolved_billing_flags > 0 ? 'border-red-500/30' : ''}
        />
        <KpiCard
          label="Reopened"
          value={kpis?.reopened_this_month ?? 0}
          subtitle="This month"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Volume Trend */}
        <ChartCard title="Ticket Volume (Last 30 Days)">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.volume_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill={BRAND.gold} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Backlog Trend */}
        <ChartCard title="Backlog Trend (12 Weeks)">
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={charts?.backlog_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="opened" fill="#60A5FA" radius={[2, 2, 0, 0]} />
              <Bar dataKey="closed" fill="#34D399" radius={[2, 2, 0, 0]} />
              <Line type="monotone" dataKey="net_backlog" stroke="#F87171" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Aging Buckets */}
        <ChartCard title="Ticket Aging (Open Tickets)">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.aging_buckets || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="bucket" type="category" tick={{ fontSize: 10, fill: '#6b7280' }} width={50} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill={BRAND.gold} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Workload Balance */}
        <ChartCard title="Workload Balance">
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

        {/* Status Distribution */}
        <ChartCard title="Tickets by Status">
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie
                data={charts?.status_distribution || []}
                dataKey="count"
                nameKey="status"
                cx="50%"
                cy="50%"
                outerRadius={90}
                innerRadius={50}
                paddingAngle={2}
              >
                {(charts?.status_distribution || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Priority Distribution */}
        <ChartCard title="Tickets by Priority">
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
                  return <Cell key={i} fill={colors[entry.priority] || BRAND.gold} />
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  )
}
