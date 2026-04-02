import { useState } from 'react'
import { useWorkQueue, useWorkQueueStats } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import GlobalFilters from '../components/GlobalFilters'
import TicketTable from '../components/TicketTable'
import ExportButtons from '../components/ExportButtons'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'
import { exportMultiSectionCSV } from '../utils/export'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  CartesianGrid,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

const PRIORITY_BAR_COLORS: Record<string, string> = {
  Critical: '#f87171', Urgent: '#f87171', High: '#fb923c',
  Medium: '#fbbf24', Low: '#60a5fa', 'Very Low': '#9ca3af',
}

const SCORE_BUCKET_COLORS: Record<string, string> = {
  Low: '#34D399',
  Medium: '#60a5fa',
  High: '#fbbf24',
  Critical: '#fb923c',
  Violated: '#f87171',
}

function thresholdColor(count: number, yellowAt: number, redAt: number): string {
  if (count === 0) return 'border-green-500/30'
  if (count <= yellowAt) return 'border-yellow-500/30'
  return 'border-red-500/30'
}

export default function WorkQueue() {
  const { toParams } = useFilterContext()
  const [unassignedOnly, setUnassignedOnly] = useState(false)

  const params = toParams()
  if (unassignedOnly) params.unassigned_only = 'true'

  const { data, isLoading } = useWorkQueue(params)
  const { data: stats } = useWorkQueueStats(params)

  const kpis = stats?.kpis
  const charts = stats?.charts

  const handleExportCSV = () => {
    const sections: { name: string; data: Record<string, any>[] }[] = []

    if (kpis) {
      sections.push({
        name: 'Queue KPIs',
        data: [{
          'Queue Depth': kpis.queue_depth,
          'Unassigned': kpis.unassigned_count,
          'SLA Violated': kpis.sla_violated_count,
          'SLA Breaching': kpis.sla_breaching_count,
          'High/Critical': kpis.high_critical_count,
          'Awaiting Tech': kpis.awaiting_tech_count,
          'No First Response': kpis.no_first_response_count,
          'Avg Age (min)': kpis.avg_age_minutes,
          'Avg Score': kpis.avg_score,
          'Median Score': kpis.median_score,
          'Avg First Response (min)': kpis.avg_first_response_minutes ?? '-',
        }],
      })
    }

    if (charts?.by_priority?.length) sections.push({ name: 'By Priority', data: charts.by_priority })
    if (charts?.by_technician?.length) sections.push({ name: 'By Technician', data: charts.by_technician })
    if (charts?.by_client?.length) sections.push({ name: 'By Client', data: charts.by_client })

    if (data?.tickets?.length) {
      sections.push({
        name: 'Tickets',
        data: data.tickets.map((t: any) => ({
          Rank: t.rank,
          ID: t.display_id,
          Subject: t.subject,
          Client: t.client_name,
          Tech: t.technician_name || 'Unassigned',
          Priority: t.priority,
          Status: t.status,
          Created: t.created_time,
          'Time (hrs)': t.worklog_hours,
          Score: t.score?.toFixed(0),
        })),
      })
    }

    exportMultiSectionCSV(sections, 'work_queue_report')
  }

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Work Queue</h2>
          <p className="text-sm text-gray-500 mt-1">
            Scored by SLA urgency, priority, age, and responsiveness. Pick from the top.
          </p>
        </div>
        <ExportButtons
          onCSV={handleExportCSV}
          pageTitle="Work Queue"
        />
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <GlobalFilters />

        <label className="flex items-center gap-2 text-xs text-gray-400">
          <input
            type="checkbox"
            checked={unassignedOnly}
            onChange={e => setUnassignedOnly(e.target.checked)}
            className="rounded border-zinc-600 bg-zinc-800 text-brand-primary-light focus:ring-brand-primary/50"
          />
          Unassigned only
        </label>

        {data?.count !== undefined && (
          <span className="text-xs text-gray-500 ml-auto">
            {data.count} tickets
          </span>
        )}
      </div>

      {/* KPI Row 1: Queue Health */}
      {kpis && (
        <div>
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-2">Queue Health</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <KpiCard
              label="Queue Depth"
              value={kpis.queue_depth}
              subtitle={`${kpis.unassigned_count} unassigned`}
              colorClass={
                kpis.queue_depth <= 20 ? 'border-green-500/30' :
                kpis.queue_depth <= 50 ? 'border-yellow-500/30' : 'border-red-500/30'
              }
            />
            <KpiCard
              label="SLA At Risk"
              value={kpis.sla_violated_count + kpis.sla_breaching_count}
              subtitle={`${kpis.sla_violated_count} violated, ${kpis.sla_breaching_count} breaching`}
              colorClass={thresholdColor(kpis.sla_violated_count + kpis.sla_breaching_count, 3, 4)}
            />
            <KpiCard
              label="Awaiting Tech"
              value={kpis.awaiting_tech_count}
              subtitle={`${kpis.no_first_response_count} with no first response`}
              colorClass={thresholdColor(kpis.awaiting_tech_count, 5, 6)}
            />
            <KpiCard
              label="High / Critical"
              value={kpis.high_critical_count}
              subtitle={`${kpis.high_critical_pct}% of queue`}
              colorClass={thresholdColor(kpis.high_critical_count, 5, 6)}
            />
          </div>
        </div>
      )}

      {/* KPI Row 2: Queue Metrics */}
      {kpis && (
        <div>
          <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-2">Queue Metrics</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            <KpiCard
              label="Avg Age"
              value={formatDuration(kpis.avg_age_minutes)}
              subtitle={`Oldest: ${formatDuration(kpis.oldest_age_minutes)}`}
              colorClass={
                kpis.avg_age_minutes <= 2880 ? 'border-green-500/30' :
                kpis.avg_age_minutes <= 7200 ? 'border-yellow-500/30' : 'border-red-500/30'
              }
            />
            <KpiCard
              label="Avg Score"
              value={kpis.avg_score}
              subtitle={`Median: ${kpis.median_score}`}
              colorClass={
                kpis.avg_score < 100 ? 'border-green-500/30' :
                kpis.avg_score < 500 ? 'border-yellow-500/30' : 'border-red-500/30'
              }
            />
            <KpiCard
              label="Avg First Response"
              value={kpis.avg_first_response_minutes != null ? formatDuration(kpis.avg_first_response_minutes) : '-'}
              subtitle={`${kpis.no_first_response_count} still waiting`}
              colorClass={
                kpis.avg_first_response_minutes == null ? '' :
                kpis.avg_first_response_minutes <= 30 ? 'border-green-500/30' :
                kpis.avg_first_response_minutes <= 120 ? 'border-yellow-500/30' : 'border-red-500/30'
              }
            />
          </div>
        </div>
      )}

      {/* Charts */}
      {charts && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Queue by Priority */}
          <ChartCard title="Queue by Priority" exportData={charts.by_priority} exportFilename="queue_by_priority">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={charts.by_priority}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="priority" tick={{ fontSize: 11, fill: '#9ca3af' }} />
                <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} allowDecimals={false} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {(charts.by_priority || []).map((entry: any, i: number) => (
                    <Cell key={i} fill={PRIORITY_BAR_COLORS[entry.priority] || BRAND.primary} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Score Distribution */}
          <ChartCard title="Score Distribution" exportData={charts.score_distribution} exportFilename="score_distribution">
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={charts.score_distribution} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} allowDecimals={false} />
                <YAxis dataKey="bucket" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={60} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {(charts.score_distribution || []).map((entry: any, i: number) => (
                    <Cell key={i} fill={SCORE_BUCKET_COLORS[entry.label] || BRAND.primary} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Queue by Technician */}
          <ChartCard title="Queue by Technician" exportData={charts.by_technician} exportFilename="queue_by_technician">
            <ResponsiveContainer width="100%" height={Math.max(250, (charts.by_technician?.length || 0) * 32)}>
              <BarChart data={charts.by_technician} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} allowDecimals={false} />
                <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={100} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="count" fill={BRAND.primary} radius={[0, 4, 4, 0]}>
                  {(charts.by_technician || []).map((entry: any, i: number) => {
                    const color = entry.name === 'Unassigned' ? '#f87171' : CHART_COLORS[i % CHART_COLORS.length]
                    return <Cell key={i} fill={color} />
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>

          {/* Queue by Client */}
          <ChartCard title="Queue by Client" exportData={charts.by_client} exportFilename="queue_by_client">
            <ResponsiveContainer width="100%" height={Math.max(250, (charts.by_client?.length || 0) * 32)}>
              <BarChart data={charts.by_client} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} allowDecimals={false} />
                <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={120} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="count" fill="#8B5CF6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      )}

      {/* Ticket Table */}
      {isLoading ? (
        <div className="text-gray-500">Loading queue...</div>
      ) : (
        <TicketTable
          tickets={data?.tickets || []}
          showRank
          showScore
          showLastResponder
          showCategory
          defaultSortKey="rank"
          defaultSortDir="asc"
          emptyMessage="Queue is empty. All caught up!"
        />
      )}
    </div>
  )
}
