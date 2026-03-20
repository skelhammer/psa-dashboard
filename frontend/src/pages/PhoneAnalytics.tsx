import { usePhoneOverview, usePhoneCharts, usePhoneAgents, usePhoneQueues } from '../api/hooks'
import { BRAND, CHART_COLORS } from '../utils/constants'
import ChartCard from '../components/ChartCard'
import clsx from 'clsx'
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

function KpiCard({ label, value, sub, colorClass }: {
  label: string; value: string | number; sub?: string; colorClass?: string
}) {
  return (
    <div className={clsx(
      'group relative overflow-hidden rounded-xl border p-5 animate-fade-in transition-all duration-200',
      'bg-[#111113] shadow-lg shadow-black/25 hover:shadow-xl hover:-translate-y-0.5',
      colorClass || 'border-white/[0.08] hover:border-white/[0.15]',
    )}>
      <div className="absolute top-0 left-0 right-0 h-[1px] opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-gradient-to-r from-transparent via-brand-primary/40 to-transparent" />
      <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest mb-2.5">{label}</p>
      <p className="text-2xl font-bold tabular-nums tracking-tight text-white">{value}</p>
      {sub && <p className="text-[11px] text-gray-500 mt-1">{sub}</p>}
    </div>
  )
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

const OUTCOME_COLORS: Record<string, string> = {
  connected: '#10B981',
  missed: '#EF4444',
  voicemail: '#F59E0B',
  abandoned: '#6B7280',
}

export default function PhoneAnalytics() {
  const { data: overview, isLoading } = usePhoneOverview()
  const { data: charts } = usePhoneCharts()
  const { data: agentData } = usePhoneAgents()
  const { data: queueData } = usePhoneQueues()

  if (isLoading) return <div className="text-gray-500">Loading phone analytics...</div>

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

  const agents = agentData?.agents || []
  const queues = queueData?.queues || []

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Header */}
      <div className="page-header">
        <h2 className="text-xl font-bold">Phone Analytics</h2>
        <p className="text-sm text-gray-500 mt-1">Call volume, agent performance, and queue metrics (last 30 days)</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard
          label="Total Calls"
          value={overview.total_calls.toLocaleString()}
          sub={`${overview.inbound} in / ${overview.outbound} out`}
        />
        <KpiCard
          label="Answer Rate"
          value={`${overview.answer_rate}%`}
          colorClass={
            overview.answer_rate >= 90 ? 'border-emerald-500/30' :
            overview.answer_rate >= 75 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Avg Speed of Answer"
          value={formatSeconds(overview.avg_wait_seconds)}
        />
        <KpiCard
          label="Avg Handle Time"
          value={formatSeconds(overview.avg_handle_seconds)}
        />
        <KpiCard
          label="Abandoned Rate"
          value={`${overview.abandoned_rate}%`}
          colorClass={
            overview.abandoned_rate <= 3 ? 'border-emerald-500/30' :
            overview.abandoned_rate <= 8 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
        <KpiCard
          label="Service Level (80/20)"
          value={`${overview.service_level}%`}
          colorClass={
            overview.service_level >= 80 ? 'border-emerald-500/30' :
            overview.service_level >= 60 ? 'border-yellow-500/30' : 'border-red-500/30'
          }
        />
      </div>

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

      {/* Agent Performance Table */}
      <ChartCard title="Agent Performance" exportData={agents} exportFilename="phone_agents">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-gray-500 border-b border-white/[0.08]">
                <th className="pb-3 pr-4">Agent</th>
                <th className="pb-3 pr-4 text-right">Calls</th>
                <th className="pb-3 pr-4 text-right">Answered</th>
                <th className="pb-3 pr-4 text-right">Missed</th>
                <th className="pb-3 pr-4 text-right">Answer %</th>
                <th className="pb-3 pr-4 text-right">Avg Handle</th>
                <th className="pb-3 text-right">Talk Time</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent: any) => (
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
                <th className="pb-3 pr-4">Queue</th>
                <th className="pb-3 pr-4 text-right">Offered</th>
                <th className="pb-3 pr-4 text-right">Answered</th>
                <th className="pb-3 pr-4 text-right">Abandoned</th>
                <th className="pb-3 pr-4 text-right">Avg Wait</th>
                <th className="pb-3 pr-4 text-right">Answer %</th>
                <th className="pb-3 text-right">SL (80/20)</th>
              </tr>
            </thead>
            <tbody>
              {queues.map((q: any) => (
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
  // Map Sunday=0 to end: Mon=1..Sat=6, Sun=0->7 for display
  const dayOrder = [1, 2, 3, 4, 5, 6, 0]
  const hours = Array.from({ length: 12 }, (_, i) => i + 7) // 7am-6pm

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
