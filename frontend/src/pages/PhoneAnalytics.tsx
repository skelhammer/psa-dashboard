import { useState, useMemo } from 'react'
import { usePhoneOverview, usePhoneCharts, usePhoneAgents, usePhoneQueues, usePhoneCallbackRate, usePhonePeakHours, usePhoneVoicemailResponse, usePhoneSyncStatus, usePhoneWaitDistribution, usePhoneDrilldown } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { BRAND, CHART_COLORS } from '../utils/constants'
import ChartCard from '../components/ChartCard'
import KpiCard from '../components/KpiCard'
import GlobalFilters from '../components/GlobalFilters'
import clsx from 'clsx'
import { ChevronUp, ChevronDown, X } from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, CartesianGrid, Cell, PieChart, Pie, Legend,
} from 'recharts'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

const OUTCOME_COLORS: Record<string, string> = {
  connected: '#10B981',
  missed: '#EF4444',
  voicemail: '#F59E0B',
  abandoned: '#6B7280',
}

const WAIT_TIER_COLORS: Record<string, string> = {
  '< 10s': '#10B981',
  '10-20s': '#84CC16',
  '20-30s': '#F59E0B',
  '30-60s': '#F97316',
  '60s+': '#EF4444',
}

function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const sec = s % 60
  if (m < 60) return sec > 0 ? `${m}m ${sec}s` : `${m}m`
  const h = Math.floor(m / 60)
  const rm = m % 60
  return rm > 0 ? `${h}h ${rm}m` : `${h}h`
}

function formatHour12(hour: number): string {
  if (hour === 0) return '12:00 AM'
  if (hour < 12) return `${hour}:00 AM`
  if (hour === 12) return '12:00 PM'
  return `${hour - 12}:00 PM`
}

function formatMinutesDuration(minutes: number): string {
  if (minutes < 0) return '0m'
  if (minutes < 60) return `${Math.round(minutes)}m`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function SyncStatusBadge({ syncStatus }: { syncStatus: any }) {
  if (!syncStatus) return null

  if (syncStatus.is_syncing) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-blue-400">
        <span className="h-2 w-2 rounded-full bg-blue-400 animate-pulse" />
        Syncing...
      </span>
    )
  }

  const hasErrors = syncStatus.last_result?.errors?.length > 0

  return (
    <span className="inline-flex items-center gap-2">
      {syncStatus.last_sync_time && (
        <span className="text-xs text-gray-500">
          Last sync: {formatMinutesDuration((Date.now() - new Date(syncStatus.last_sync_time).getTime()) / 60000)} ago
        </span>
      )}
      {hasErrors && (
        <span className="inline-flex items-center gap-1 text-xs text-yellow-400 bg-yellow-500/10 rounded-full px-2 py-0.5">
          <span className="h-1.5 w-1.5 rounded-full bg-yellow-400" />
          Sync warnings
        </span>
      )}
    </span>
  )
}

const METRIC_LABELS: Record<string, string> = {
  answer_rate: 'Answer Rate',
  abandoned: 'Abandon Rate',
  avg_wait: 'Avg Wait Time',
  service_level: 'Service Level',
  hold_time: 'Hold Time',
}

const METRIC_UNITS: Record<string, string> = {
  answer_rate: '%',
  abandoned: '%',
  avg_wait: 's',
  service_level: '%',
  hold_time: 's',
}

type SortDir = 'asc' | 'desc'

function useSortable<T>(data: T[], defaultKey: string, defaultDir: SortDir = 'desc') {
  const [sortKey, setSortKey] = useState(defaultKey)
  const [sortDir, setSortDir] = useState<SortDir>(defaultDir)

  const handleSort = (key: string) => {
    if (key === sortKey) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    return [...data].sort((a: any, b: any) => {
      const av = a[sortKey] ?? 0
      const bv = b[sortKey] ?? 0
      const cmp = typeof av === 'string' ? av.localeCompare(bv) : av - bv
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [data, sortKey, sortDir])

  return { sorted, sortKey, sortDir, handleSort }
}

function SortHeader({ label, sortKey, currentKey, currentDir, onSort, align = 'right' }: {
  label: string; sortKey: string; currentKey: string; currentDir: SortDir; onSort: (k: string) => void; align?: string
}) {
  const active = sortKey === currentKey
  return (
    <th
      className={clsx('pb-3 pr-4 cursor-pointer select-none hover:text-gray-300 transition-colors', align === 'right' ? 'text-right' : 'text-left')}
      onClick={() => onSort(sortKey)}
    >
      <span className="inline-flex items-center gap-0.5">
        {label}
        {active && (currentDir === 'asc'
          ? <ChevronUp size={12} className="text-brand-primary" />
          : <ChevronDown size={12} className="text-brand-primary" />
        )}
      </span>
    </th>
  )
}

export default function PhoneAnalytics() {
  const { toParams } = useFilterContext()
  const [excludeInternal, setExcludeInternal] = useState(false)
  const [activeMetric, setActiveMetric] = useState<string | null>(null)

  const baseParams = toParams()
  const params = excludeInternal ? { ...baseParams, exclude_internal: 'true' } : baseParams

  const { data: overview, isLoading } = usePhoneOverview(params)
  const { data: charts } = usePhoneCharts(params)
  const { data: agentData } = usePhoneAgents(params)
  const { data: queueData } = usePhoneQueues(params)
  const { data: callbackData } = usePhoneCallbackRate(params)
  const { data: peakData } = usePhonePeakHours(params)
  const { data: vmResponseData } = usePhoneVoicemailResponse(params)
  const { data: syncStatus } = usePhoneSyncStatus()
  const { data: waitDistData } = usePhoneWaitDistribution(params)
  const { data: drilldownData, isLoading: drilldownLoading } = usePhoneDrilldown(activeMetric, params)

  const agents = agentData?.agents || []
  const queues = queueData?.queues || []
  const agentSort = useSortable(agents, 'total_calls')
  const queueSort = useSortable(queues, 'offered')
  const cmp = overview?.comparison

  if (isLoading && !overview) return <div className="text-gray-500">Loading phone analytics...</div>

  if (!overview || overview.total_calls === 0) {
    return (
      <div className="space-y-6 animate-slide-up">
        <div className="page-header">
          <h2 className="text-xl font-bold">Phone Analytics</h2>
          <p className="text-sm text-gray-500 mt-1">No phone data available. Check phone provider configuration.</p>
        </div>
      </div>
    )
  }

  const handleKpiClick = (metric: string) => {
    setActiveMetric(prev => prev === metric ? null : metric)
  }

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="text-xl font-bold">Phone Analytics</h2>
          <SyncStatusBadge syncStatus={syncStatus} />
          {/* Internal call filter toggle */}
          <label className="inline-flex items-center gap-2 text-xs text-gray-400 ml-auto cursor-pointer select-none">
            <input
              type="checkbox"
              checked={excludeInternal}
              onChange={e => setExcludeInternal(e.target.checked)}
              className="rounded border-gray-600 bg-gray-800 text-brand-primary focus:ring-brand-primary/50 h-3.5 w-3.5"
            />
            Hide internal calls
          </label>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          Call volume, agent performance, and queue metrics
          {overview?.date_range_label ? ` (${overview.date_range_label})` : ''}
        </p>
      </div>

      {/* Filters */}
      <GlobalFilters />

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KpiCard
          label="Total Calls"
          value={overview.total_calls.toLocaleString()}
          subtitle={`${overview.inbound} in / ${overview.outbound} out`}
          pctChange={cmp?.total_calls_pct}
          changeDirection="up-good"
        />
        <KpiCard
          label="Answer Rate"
          value={`${overview.answer_rate}%`}
          pctChange={cmp?.answer_rate_pct}
          changeDirection="up-good"
          onClick={() => handleKpiClick('answer_rate')}
          colorClass={
            overview.answer_rate >= 90 ? 'border-emerald-500/30' :
            overview.answer_rate >= 75 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Avg Speed of Answer"
          value={formatSeconds(overview.avg_wait_seconds)}
          pctChange={cmp?.avg_wait_pct}
          changeDirection="down-good"
          onClick={() => handleKpiClick('avg_wait')}
        />
        <KpiCard
          label="Avg Handle Time"
          value={formatSeconds(overview.avg_handle_seconds)}
          pctChange={cmp?.avg_handle_pct}
          changeDirection="down-good"
        />
        <KpiCard
          label="Avg Hold Time"
          value={formatSeconds(overview.avg_hold_seconds ?? 0)}
          pctChange={cmp?.avg_hold_pct}
          changeDirection="down-good"
          onClick={() => handleKpiClick('hold_time')}
          colorClass={
            (overview.avg_hold_seconds ?? 0) <= 30 ? 'border-emerald-500/30' :
            (overview.avg_hold_seconds ?? 0) <= 120 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Abandoned Rate"
          value={`${overview.abandoned_rate}%`}
          pctChange={cmp?.abandoned_rate_pct}
          changeDirection="down-good"
          onClick={() => handleKpiClick('abandoned')}
          colorClass={
            overview.abandoned_rate <= 3 ? 'border-emerald-500/30' :
            overview.abandoned_rate <= 8 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Service Level (80/20)"
          value={`${overview.service_level}%`}
          pctChange={cmp?.service_level_pct}
          changeDirection="up-good"
          onClick={() => handleKpiClick('service_level')}
          colorClass={
            overview.service_level >= 80 ? 'border-emerald-500/30' :
            overview.service_level >= 60 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Callback Rate"
          value={`${callbackData?.callback_rate?.toFixed(1) ?? '0'}%`}
          subtitle={`${callbackData?.repeat_callers ?? 0} repeat callers`}
          colorClass={
            (callbackData?.callback_rate ?? 0) <= 15 ? 'border-emerald-500/30' :
            (callbackData?.callback_rate ?? 0) <= 25 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Busiest Hour"
          value={peakData?.busiest_hour != null ? formatHour12(peakData.busiest_hour) : '--'}
          subtitle={`${peakData?.peak_hours?.[0]?.avg_calls?.toFixed(0) ?? '?'} avg calls`}
          colorClass="border-blue-500/30"
        />
        <KpiCard
          label="VM Response Time"
          value={vmResponseData?.avg_response_minutes != null && vmResponseData.avg_response_minutes > 0 ? formatMinutesDuration(vmResponseData.avg_response_minutes) : '--'}
          subtitle={`${vmResponseData?.response_rate?.toFixed(0) ?? 0}% responded`}
          colorClass={
            (vmResponseData?.avg_response_minutes ?? 999) <= 60 ? 'border-emerald-500/30' :
            (vmResponseData?.avg_response_minutes ?? 999) <= 180 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
      </div>

      {/* KPI Drill-Down Panel */}
      {activeMetric && (
        <div className="rounded-xl border border-white/[0.08] bg-[#111113] p-5 animate-fade-in">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-200">
              {METRIC_LABELS[activeMetric] || activeMetric} Breakdown
              {drilldownData?.items && (
                <span className="ml-2 text-xs text-gray-500 font-normal">
                  Team avg: {drilldownData.team_average}{METRIC_UNITS[activeMetric] || ''}
                </span>
              )}
            </h3>
            <button
              onClick={() => setActiveMetric(null)}
              className="text-gray-500 hover:text-gray-300 transition-colors"
            >
              <X size={16} />
            </button>
          </div>
          {drilldownLoading ? (
            <p className="text-sm text-gray-500">Loading...</p>
          ) : drilldownData?.items?.length > 0 ? (
            <div className="space-y-2">
              {drilldownData.items.slice(0, 15).map((item: any, i: number) => {
                const isWorse = activeMetric === 'answer_rate' || activeMetric === 'service_level'
                  ? item.gap < 0
                  : item.gap > 0
                const barColor = isWorse ? 'bg-red-500/60' : 'bg-emerald-500/60'
                const maxVal = Math.max(...drilldownData.items.map((x: any) => Math.abs(x.value)), 1)
                const barWidth = Math.max(5, (Math.abs(item.value) / maxVal) * 100)
                return (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-gray-400 w-28 truncate shrink-0" title={item.name}>{item.name}</span>
                    <div className="flex-1 h-5 bg-white/[0.03] rounded-sm overflow-hidden relative">
                      <div className={clsx('h-full rounded-sm transition-all', barColor)} style={{ width: `${barWidth}%` }} />
                    </div>
                    <span className={clsx('text-xs font-semibold tabular-nums w-14 text-right', isWorse ? 'text-red-400' : 'text-emerald-400')}>
                      {item.value}{METRIC_UNITS[activeMetric] || ''}
                    </span>
                    <span className="text-[10px] text-gray-600 w-12 text-right tabular-nums">
                      {item.total_calls} calls
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-sm text-gray-500">No data available</p>
          )}
        </div>
      )}

      {/* Charts Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Call Volume by Hour" exportData={charts?.volume_by_hour} exportFilename="calls_by_hour">
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={charts?.volume_by_hour || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Area type="monotone" dataKey="connected" stackId="1" fill="#10B981" stroke="#10B981" fillOpacity={0.6} name="Connected" />
              <Area type="monotone" dataKey="missed" stackId="1" fill="#EF4444" stroke="#EF4444" fillOpacity={0.6} name="Missed" />
              <Area type="monotone" dataKey="voicemail" stackId="1" fill="#F59E0B" stroke="#F59E0B" fillOpacity={0.6} name="Voicemail" />
              <Area type="monotone" dataKey="abandoned" stackId="1" fill="#6B7280" stroke="#6B7280" fillOpacity={0.6} name="Abandoned" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Daily Call Trend" exportData={charts?.daily_trend} exportFilename="daily_calls">
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={charts?.daily_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: '#6b7280' }}
                tickFormatter={(v: string) => {
                  const d = new Date(v)
                  return `${d.getMonth() + 1}/${d.getDate()}`
                }}
              />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
              <Bar dataKey="inbound" fill={BRAND.primary} radius={[2, 2, 0, 0]} name="Inbound" />
              <Bar dataKey="outbound" fill="#06B6D4" radius={[2, 2, 0, 0]} name="Outbound" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Charts Row 2 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="Outcome Distribution" exportData={charts?.outcome_distribution} exportFilename="call_outcomes">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={charts?.outcome_distribution || []}
                cx="50%" cy="50%"
                innerRadius={60} outerRadius={100}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
              >
                {(charts?.outcome_distribution || []).map((entry: any, i: number) => (
                  <Cell key={i} fill={OUTCOME_COLORS[entry.name] || CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Heatmap as a table */}
        <ChartCard title="Call Volume Heatmap (Day x Hour)">
          <div className="overflow-x-auto">
            <HeatmapTable data={charts?.heatmap || []} />
          </div>
        </ChartCard>
      </div>

      {/* Charts Row 3: Wait Time Distribution */}
      {waitDistData?.tiers && waitDistData.tiers.some((t: any) => t.count > 0) && (
        <ChartCard title="Wait Time Distribution (Inbound Answered)" exportData={waitDistData?.tiers} exportFilename="wait_distribution">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={waitDistData.tiers} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis type="category" dataKey="label" tick={{ fontSize: 11, fill: '#9ca3af' }} width={55} />
              <Tooltip
                {...tooltipStyle}
                formatter={(value: number, _: any, props: any) => [`${value} (${props.payload.pct}%)`, 'Calls']}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Calls">
                {waitDistData.tiers.map((entry: any, i: number) => (
                  <Cell key={i} fill={WAIT_TIER_COLORS[entry.label] || '#6B7280'} fillOpacity={0.8} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      )}

      {/* Agent Performance Table */}
      <ChartCard title="Agent Performance" exportData={agents} exportFilename="phone_agents">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-gray-500 border-b border-white/[0.08]">
                <SortHeader label="Agent" sortKey="name" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} align="left" />
                <SortHeader label="Calls" sortKey="total_calls" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} />
                <SortHeader label="Answered" sortKey="answered" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} />
                <SortHeader label="Missed" sortKey="missed" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} />
                <SortHeader label="Answer %" sortKey="answer_rate" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} />
                <SortHeader label="Avg Handle" sortKey="avg_handle_seconds" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} />
                <SortHeader label="Talk Time" sortKey="talk_hours" currentKey={agentSort.sortKey} currentDir={agentSort.sortDir} onSort={agentSort.handleSort} />
              </tr>
            </thead>
            <tbody>
              {agentSort.sorted.map((agent: any) => (
                <tr key={agent.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="py-3 pr-4">
                    <div>
                      <span className="font-medium text-gray-200">{agent.name}</span>
                      <span className="text-xs text-gray-500 ml-2">x{agent.extension}</span>
                    </div>
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums">{agent.total_calls}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-emerald-400">{agent.answered}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-red-400">{agent.missed}</td>
                  <td className={clsx('py-3 pr-4 text-right tabular-nums font-semibold',
                    agent.answer_rate >= 90 ? 'text-emerald-400' :
                    agent.answer_rate >= 75 ? 'text-yellow-400' : 'text-red-400'
                  )}>
                    {agent.answer_rate}%
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums text-gray-400">
                    {formatSeconds(agent.avg_handle_seconds)}
                  </td>
                  <td className="py-3 text-right tabular-nums text-gray-400">{agent.talk_hours}h</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>

      {/* Queue Performance Table */}
      <ChartCard title="Queue Performance" exportData={queues} exportFilename="phone_queues">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-gray-500 border-b border-white/[0.08]">
                <SortHeader label="Queue" sortKey="name" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} align="left" />
                <SortHeader label="Offered" sortKey="offered" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} />
                <SortHeader label="Answered" sortKey="answered" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} />
                <SortHeader label="Abandoned" sortKey="abandoned" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} />
                <SortHeader label="Avg Wait" sortKey="avg_wait_seconds" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} />
                <SortHeader label="Answer %" sortKey="answer_rate" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} />
                <SortHeader label="SL (80/20)" sortKey="service_level" currentKey={queueSort.sortKey} currentDir={queueSort.sortDir} onSort={queueSort.handleSort} />
              </tr>
            </thead>
            <tbody>
              {queueSort.sorted.map((q: any) => (
                <tr key={q.id} className="border-b border-white/[0.04] hover:bg-white/[0.02]">
                  <td className="py-3 pr-4">
                    <div>
                      <span className="font-medium text-gray-200">{q.name}</span>
                      <span className="text-xs text-gray-500 ml-2">x{q.extension} ({q.member_count} agents)</span>
                    </div>
                  </td>
                  <td className="py-3 pr-4 text-right tabular-nums">{q.offered}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-emerald-400">{q.answered}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-red-400">{q.abandoned}</td>
                  <td className="py-3 pr-4 text-right tabular-nums text-gray-400">
                    {formatSeconds(q.avg_wait_seconds)}
                  </td>
                  <td className={clsx('py-3 pr-4 text-right tabular-nums font-semibold',
                    q.answer_rate >= 90 ? 'text-emerald-400' :
                    q.answer_rate >= 75 ? 'text-yellow-400' : 'text-red-400'
                  )}>
                    {q.answer_rate}%
                  </td>
                  <td className={clsx('py-3 text-right tabular-nums font-semibold',
                    q.service_level >= 80 ? 'text-emerald-400' :
                    q.service_level >= 60 ? 'text-yellow-400' : 'text-red-400'
                  )}>
                    {q.service_level}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </ChartCard>
    </div>
  )
}


function HeatmapTable({ data }: { data: any[] }) {
  if (!data.length) return <p className="text-gray-500 text-sm p-4">No heatmap data</p>

  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const dayOrder = [1, 2, 3, 4, 5, 6, 0]

  // Derive hours dynamically from the data
  const activeHours = data.map(d => d.hour)
  const minHour = Math.max(0, Math.min(...activeHours) - 1)
  const maxHour = Math.min(23, Math.max(...activeHours) + 1)
  const hours = Array.from({ length: maxHour - minHour + 1 }, (_, i) => i + minHour)

  // Build lookup
  const lookup: Record<string, number> = {}
  let maxCount = 1
  for (const d of data) {
    const key = `${d.day_num}-${d.hour}`
    lookup[key] = d.count
    if (d.count > maxCount) maxCount = d.count
  }

  const getColor = (count: number) => {
    if (count === 0) return 'bg-white/[0.02]'
    const intensity = count / maxCount
    if (intensity > 0.75) return 'bg-blue-500/60'
    if (intensity > 0.5) return 'bg-blue-500/40'
    if (intensity > 0.25) return 'bg-blue-500/25'
    return 'bg-blue-500/10'
  }

  return (
    <table className="text-[10px] w-full">
      <thead>
        <tr>
          <th className="pb-1 pr-1 text-left text-gray-500"></th>
          {hours.map(h => (
            <th key={h} className="pb-1 px-0.5 text-center text-gray-500 font-medium">
              {h > 12 ? `${h - 12}p` : h === 12 ? '12p' : `${h}a`}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {dayOrder.map(dayNum => (
          <tr key={dayNum}>
            <td className="pr-2 py-0.5 text-gray-500 font-medium">{days[dayNum === 0 ? 6 : dayNum - 1]}</td>
            {hours.map(h => {
              const count = lookup[`${dayNum}-${h}`] || 0
              return (
                <td key={h} className="px-0.5 py-0.5">
                  <div
                    className={clsx('rounded-sm h-6 w-full flex items-center justify-center', getColor(count))}
                    title={`${count} calls`}
                  >
                    {count > 0 && <span className="text-white/70">{count}</span>}
                  </div>
                </td>
              )
            })}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
