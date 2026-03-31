import { useParams, useNavigate } from 'react-router-dom'
import { useClientDetail } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'
import TicketTable from '../components/TicketTable'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  LineChart, Line, CartesianGrid, ComposedChart, Cell,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

export default function ClientDetail() {
  const { clientId } = useParams()
  const navigate = useNavigate()
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useClientDetail(clientId, params)

  if (isLoading && !data) return <div className="text-gray-500">Loading...</div>
  if (data?.error) return <div className="text-red-400">{data.error}</div>

  const client = data?.client
  const kpis = data?.kpis
  const periodLabel = data?.date_range_label

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header flex items-center gap-3">
        <button
          onClick={() => navigate('/clients')}
          className="text-sm text-gray-500 hover:text-gray-300"
        >
          &larr; Back
        </button>
        <h2 className="text-xl font-bold">{client?.name}</h2>
        <span className="text-xs text-gray-500 bg-zinc-800 px-2 py-0.5 rounded-full">{client?.stage}</span>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label="Open Tickets" value={kpis?.open_tickets ?? '-'} />
        <KpiCard label="Closed (Period)" value={kpis?.closed_period ?? '-'} subtitle={periodLabel} />
        <KpiCard
          label="SLA Compliance"
          value={`${kpis?.sla_compliance_pct ?? '-'}%`}
          subtitle={periodLabel}
          colorClass={
            (kpis?.sla_compliance_pct ?? 100) >= 95 ? 'border-green-500/30' :
            (kpis?.sla_compliance_pct ?? 100) >= 80 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Avg First Response"
          value={kpis?.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-'}
          subtitle={periodLabel}
        />
        <KpiCard
          label="Avg Resolution"
          value={kpis?.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-'}
          subtitle={periodLabel}
        />
        <KpiCard label="Billed Hours" value={kpis?.billed_hours ?? '-'} subtitle={periodLabel} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* SLA Compliance Trend */}
        <ChartCard title="SLA Compliance Trend (12 Weeks)">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data?.sla_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} domain={['dataMin - 5', 100]} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip {...tooltipStyle} />
              <Line
                type="monotone"
                dataKey="compliance_pct"
                stroke={BRAND.primary}
                strokeWidth={2}
                dot={{ fill: BRAND.primary, r: 3 }}
                name="SLA %"
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Volume Trend */}
        <ChartCard title="Ticket Volume Trend (12 Weeks)">
          <ResponsiveContainer width="100%" height={250}>
            <ComposedChart data={data?.volume_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="created" fill="#60A5FA" radius={[2, 2, 0, 0]} name="Created" />
              <Bar dataKey="closed" fill="#34D399" radius={[2, 2, 0, 0]} name="Closed" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Category Breakdown */}
        <ChartCard title="Tickets by Category">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.categories || []} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="category" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={100} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {(data?.categories || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Technician Breakdown */}
        <ChartCard title="Tickets by Technician">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.technicians || []} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="technician" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={100} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill={BRAND.primary} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Open Tickets */}
      <div>
        <h3 className="text-lg font-semibold mb-3">
          Open Tickets
          <span className="text-xs text-gray-500 ml-2">({data?.open_tickets?.length || 0})</span>
        </h3>
        <TicketTable
          tickets={data?.open_tickets || []}
          emptyMessage="No open tickets for this client."
        />
      </div>
    </div>
  )
}
