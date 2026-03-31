import { useParams, useNavigate } from 'react-router-dom'
import { useTechnicianDetail } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import GlobalFilters from '../components/GlobalFilters'
import KpiCard from '../components/KpiCard'
import TicketTable from '../components/TicketTable'
import ChartCard from '../components/ChartCard'
import ExportButtons from '../components/ExportButtons'
import clsx from 'clsx'
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis,
  Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { CHART_COLORS, BRAND } from '../utils/constants'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

function slaColor(pct: number): string {
  if (pct >= 95) return 'border-green-500/50 bg-green-500/5'
  if (pct >= 80) return 'border-yellow-500/50 bg-yellow-500/5'
  return 'border-red-500/50 bg-red-500/5'
}

export default function TechnicianDetail() {
  const { techId } = useParams()
  const navigate = useNavigate()
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useTechnicianDetail(techId, params)

  if (isLoading && !data) return <div className="text-gray-500">Loading...</div>
  if (data?.error) return <div className="text-red-400">{data.error}</div>

  const tech = data?.technician
  const kpis = data?.kpis || {}

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/technicians')}
            className="text-sm text-gray-500 hover:text-gray-300"
          >
            &larr; Back
          </button>
          <h2 className="text-xl font-bold">{tech?.name}</h2>
          <span className="text-xs text-gray-500 bg-zinc-800 px-2 py-0.5 rounded-full">{tech?.role}</span>
        </div>
        <ExportButtons
          csvData={data?.open_tickets}
          csvFilename={`technician_${tech?.name || techId}_tickets`}
          pageTitle={`Technician: ${tech?.name || ''}`}
        />
      </div>

      {/* Global Filters */}
      <GlobalFilters />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="Open Tickets"
          value={kpis.open_tickets ?? 0}
        />
        <KpiCard
          label="Closed"
          value={kpis.closed_period ?? 0}
          subtitle="this period"
        />
        <KpiCard
          label="Avg First Response"
          value={formatDuration(kpis.avg_first_response_minutes ?? 0)}
        />
        <KpiCard
          label="Avg Resolution"
          value={formatDuration(kpis.avg_resolution_minutes ?? 0)}
        />
        <KpiCard
          label="SLA Compliance"
          value={`${kpis.sla_compliance_pct ?? 0}%`}
          colorClass={slaColor(kpis.sla_compliance_pct ?? 0)}
        />
        <KpiCard
          label="Hours Logged"
          value={`${kpis.worklog_hours ?? 0}h`}
          subtitle={`${kpis.utilization_pct ?? 0}% utilization`}
        />
      </div>

      {/* Charts Row: Volume Trend + SLA Compliance Trend */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title="Weekly Volume"
          exportData={data?.volume_trend}
          exportFilename={`tech_${techId}_volume_trend`}
        >
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data?.volume_trend || []}>
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="created" name="Created" fill={BRAND.primary} radius={[4, 4, 0, 0]} />
              <Bar dataKey="closed" name="Closed" fill="#6b7280" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="SLA Compliance Trend"
          exportData={data?.sla_trend}
          exportFilename={`tech_${techId}_sla_trend`}
        >
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data?.sla_trend || []}>
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis domain={['dataMin - 5', 100]} tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v: number) => `${v}%`} />
              <Tooltip {...tooltipStyle} />
              <ReferenceLine y={95} stroke="#374151" strokeDasharray="3 3" label={{ value: '95%', fill: '#6b7280', fontSize: 10 }} />
              <Line
                type="monotone"
                dataKey="compliance_pct"
                name="SLA %"
                stroke={BRAND.primary}
                strokeWidth={2}
                dot={{ fill: BRAND.primary, r: 3 }}
                activeDot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Breakdown Row: Category + Client */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard
          title="Tickets by Category"
          exportData={data?.categories}
          exportFilename={`tech_${techId}_categories`}
        >
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.categories || []} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="category" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={80} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {(data?.categories || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          title="Tickets by Client"
          exportData={data?.clients}
          exportFilename={`tech_${techId}_clients`}
        >
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data?.clients || []} layout="vertical">
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="client" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={120} />
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
          emptyMessage="No open tickets assigned."
        />
      </div>

      {/* Recently Closed */}
      <div>
        <h3 className="text-lg font-semibold mb-3">
          Recently Closed
          <span className="text-xs text-gray-500 ml-2">({data?.recent_closed?.length || 0})</span>
        </h3>
        <TicketTable
          tickets={data?.recent_closed || []}
          emptyMessage="No recently closed tickets."
        />
      </div>
    </div>
  )
}
