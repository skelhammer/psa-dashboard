import { useNavigate } from 'react-router-dom'
import { useOverview, useOverviewCharts, useManageToZero, usePhoneOverview } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { formatDuration } from '../utils/formatting'
import { BRAND, CHART_COLORS } from '../utils/constants'
import KpiCard from '../components/KpiCard'
import ChartCard from '../components/ChartCard'
import GlobalFilters from '../components/GlobalFilters'
import ExportButtons from '../components/ExportButtons'
import { exportMultiSectionCSV } from '../utils/export'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, CartesianGrid, Legend,
  ReferenceLine, Treemap,
} from 'recharts'
import { AlertTriangle } from 'lucide-react'

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' },
  labelStyle: { color: '#9ca3af' },
  itemStyle: { color: '#d1d5db' },
  cursor: { fill: 'rgba(59, 130, 246, 0.1)' },
}

// Custom treemap tile: brand-blue rectangle with an HTML label inside a
// foreignObject, so the browser uses its normal HTML text rendering pipeline
// (sub-pixel anti-aliasing, proper kerning) instead of the chunky SVG text
// path. CSS text-overflow handles label truncation per tile.
function SubcategoryTreemapTile(props: any) {
  const { x, y, width, height, name, value, depth } = props
  // depth 0 is the implicit root container; only draw leaves.
  if (depth === 0) return null

  const canShowLabel = width > 32 && height > 18
  const canShowValue = width > 32 && height > 32

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        style={{
          fill: BRAND.primary,
          stroke: '#0a0a0a',
          strokeWidth: 2,
          fillOpacity: 0.85,
        }}
      />
      {canShowLabel && (
        <foreignObject x={x} y={y} width={width} height={height}>
          <div
            // @ts-ignore - xmlns is required for proper foreignObject HTML
            xmlns="http://www.w3.org/1999/xhtml"
            style={{
              boxSizing: 'border-box',
              width: '100%',
              height: '100%',
              padding: '4px 6px',
              color: '#ffffff',
              fontFamily:
                "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif",
              fontSize: 11,
              fontWeight: 600,
              lineHeight: 1.2,
              overflow: 'hidden',
              pointerEvents: 'none',
            }}
          >
            <div
              style={{
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                textOverflow: 'ellipsis',
              }}
            >
              {name}
            </div>
            {canShowValue && (
              <div
                style={{
                  color: '#dbeafe',
                  fontSize: 10,
                  fontWeight: 400,
                  marginTop: 1,
                }}
              >
                {value}
              </div>
            )}
          </div>
        </foreignObject>
      )}
    </g>
  )
}

const MTZ_CARDS = [
  { key: 'unassigned', label: 'Unassigned' },
  { key: 'no_first_response', label: 'No Response' },
  { key: 'awaiting_tech_reply', label: 'Awaiting Reply' },
  { key: 'stale', label: 'Stale' },
  { key: 'sla_breaching_soon', label: 'SLA Breaching' },
  { key: 'sla_violated', label: 'SLA Violated' },
  { key: 'unresolved_billing_flags', label: 'Billing Flags' },
] as const

export default function Overview() {
  const navigate = useNavigate()
  const { toParams } = useFilterContext()
  const params = toParams()
  const { data, isLoading } = useOverview(params)
  const { data: charts } = useOverviewCharts(params)
  const { data: mtzData } = useManageToZero(params)
  const { data: phoneData } = usePhoneOverview(params)

  if (isLoading && !data) {
    return <div className="text-gray-500">Loading overview...</div>
  }

  const kpis = data?.kpis
  const pct = data?.pct_change
  const periodLabel = data?.date_range_label
  const thresholds = data?.thresholds
  const mtzCards = mtzData?.cards

  // Threshold coloring for response/resolution
  const frTarget = thresholds?.first_response_target_minutes ?? 30
  const resTarget = thresholds?.resolution_target_minutes ?? 240
  const frMinutes = kpis?.avg_first_response_minutes ?? 0
  const resMinutes = kpis?.avg_resolution_minutes ?? 0

  const frColor = frMinutes <= 0 ? '' :
    frMinutes <= frTarget ? 'border-green-500/30' :
    frMinutes <= frTarget * 2 ? 'border-yellow-500/30' : 'border-red-500/30'

  const resColor = resMinutes <= 0 ? '' :
    resMinutes <= resTarget ? 'border-green-500/30' :
    resMinutes <= resTarget * 2 ? 'border-yellow-500/30' : 'border-red-500/30'

  // Net flow formatting
  const netFlowToday = kpis?.net_flow_today ?? 0
  const netFlowPeriod = kpis?.net_flow_period ?? 0
  const netFlowTodayStr = `${netFlowToday > 0 ? '+' : ''}${netFlowToday}`
  const netFlowPeriodStr = `${netFlowPeriod > 0 ? '+' : ''}${netFlowPeriod}`

  // Workload balance threshold coloring
  const workloadData = charts?.workload_balance || []
  const avgLoad = workloadData.length > 0
    ? workloadData.reduce((sum: number, d: any) => sum + d.count, 0) / workloadData.length
    : 0

  const handleExportCSV = () => {
    const sections: { name: string; data: Record<string, any>[] }[] = []

    if (kpis) {
      sections.push({
        name: 'KPI Summary',
        data: [{
          'Open Tickets': kpis.total_open,
          'Net Flow Today': netFlowToday,
          'SLA Compliance %': kpis.sla_compliance_pct,
          'Avg First Response': kpis.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-',
          'Avg Resolution': kpis.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-',
          'Reopened': kpis.reopened_period,
          'Worklog Hours': kpis.total_worklog_hours,
          'Created (Period)': kpis.created_period,
          'Closed (Period)': kpis.closed_period,
          'Net Flow (Period)': netFlowPeriod,
        }],
      })
    }
    if (charts?.volume_trend?.length) sections.push({ name: 'Volume Trend', data: charts.volume_trend })
    if (charts?.daily_new_tickets?.length) sections.push({ name: 'New Tickets Per Day', data: charts.daily_new_tickets })
    if (charts?.aging_buckets?.length) sections.push({ name: 'Ticket Aging', data: charts.aging_buckets })
    if (charts?.workload_balance?.length) sections.push({ name: 'Workload Balance', data: charts.workload_balance })
    if (charts?.group_distribution?.length) sections.push({ name: 'Open Tickets by Group', data: charts.group_distribution })
    if (charts?.status_distribution?.length) sections.push({ name: 'Open Tickets by Status', data: charts.status_distribution })
    if (charts?.priority_distribution?.length) sections.push({ name: 'Open Tickets by Priority', data: charts.priority_distribution })
    if (charts?.category_distribution?.length) sections.push({ name: 'Open Tickets by Category', data: charts.category_distribution })
    if (charts?.subcategory_distribution?.length) sections.push({ name: 'Open Tickets by Subcategory', data: charts.subcategory_distribution })
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

      {/* MTZ Action Bar */}
      {mtzCards && (
        <div
          className="flex items-center gap-2 p-3 rounded-xl bg-[#111113] border border-white/[0.06] cursor-pointer hover:border-white/[0.12] transition-colors"
          onClick={() => navigate('/manage-to-zero')}
        >
          <AlertTriangle size={14} className="text-gray-500 shrink-0" />
          <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest shrink-0">Action Items</span>
          <div className="flex items-center gap-3 ml-2 flex-wrap">
            {MTZ_CARDS.map(({ key, label }) => {
              const val = mtzCards[key] ?? 0
              return (
                <span
                  key={key}
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                    val > 0
                      ? 'bg-red-500/15 text-red-400'
                      : 'bg-emerald-500/10 text-emerald-500/60'
                  }`}
                >
                  {label}: {val}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Row 1: Right Now */}
      <div>
        <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-2">Right Now</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Open Tickets" value={kpis?.total_open ?? '-'} onClick={() => navigate('/manage-to-zero')} />
          <KpiCard
            label="Net Flow Today"
            value={netFlowTodayStr}
            subtitle={`Created ${kpis?.created_today ?? 0} / Closed ${kpis?.closed_today ?? 0}`}
            colorClass={netFlowToday <= 0 ? 'border-green-500/30' : 'border-red-500/30'}
            onClick={() => navigate('/work-queue')}
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
          {phoneData && phoneData.total_calls > 0 ? (
            <KpiCard
              label="Phone Answer Rate"
              value={`${phoneData.answer_rate ?? 0}%`}
              subtitle={periodLabel}
              colorClass={
                (phoneData.answer_rate ?? 100) >= 90 ? 'border-green-500/30' :
                (phoneData.answer_rate ?? 100) >= 75 ? 'border-yellow-500/30' : 'border-red-500/30'
              }
              pctChange={phoneData.comparison?.answer_rate_pct}
              changeDirection="up-good"
              onClick={() => navigate('/phone')}
            />
          ) : (
            <KpiCard
              label="Created / Closed This Week"
              value={`${kpis?.created_this_week ?? 0} / ${kpis?.closed_this_week ?? 0}`}
              colorClass={
                (kpis?.closed_this_week ?? 0) >= (kpis?.created_this_week ?? 0)
                  ? 'border-green-500/30' : 'border-red-500/30'
              }
              onClick={() => navigate('/manage-to-zero')}
            />
          )}
        </div>
        {/* Sub-row: Created/Closed Today & This Week */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
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
        </div>
      </div>

      {/* Row 2: Period Performance */}
      <div>
        <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-2">Period Performance</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <KpiCard
            label="Avg First Response"
            value={kpis?.avg_first_response_minutes ? formatDuration(kpis.avg_first_response_minutes) : '-'}
            subtitle={periodLabel}
            colorClass={frColor}
            pctChange={pct?.avg_first_response_minutes}
            changeDirection="down-good"
            onClick={() => navigate('/technicians')}
          />
          <KpiCard
            label="Avg Resolution"
            value={kpis?.avg_resolution_minutes ? formatDuration(kpis.avg_resolution_minutes) : '-'}
            subtitle={periodLabel}
            colorClass={resColor}
            pctChange={pct?.avg_resolution_minutes}
            changeDirection="down-good"
            onClick={() => navigate('/technicians')}
          />
          <KpiCard
            label="FCR Rate"
            value={`${kpis?.fcr_rate ?? 0}%`}
            subtitle={`${kpis?.fcr_count ?? 0} / ${kpis?.fcr_total ?? 0} closed`}
            colorClass={
              (kpis?.fcr_rate ?? 0) >= 70 ? 'border-green-500/30' :
              (kpis?.fcr_rate ?? 0) >= 50 ? 'border-yellow-500/30' : 'border-red-500/30'
            }
            pctChange={pct?.fcr_rate}
            changeDirection="up-good"
          />
          <KpiCard
            label="Reopened"
            value={kpis?.reopened_period ?? 0}
            subtitle={periodLabel}
            pctChange={pct?.reopened_period}
            changeDirection="down-good"
            onClick={() => navigate('/work-queue')}
          />
          <KpiCard
            label="Worklog Hours"
            value={kpis?.total_worklog_hours ?? '-'}
            subtitle={periodLabel}
            pctChange={pct?.total_worklog_hours}
            changeDirection="up-good"
            onClick={() => navigate('/technicians')}
          />
        </div>
      </div>

      {/* Row 3: Throughput */}
      <div>
        <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest mb-2">Throughput</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <KpiCard
            label="Created (Period)"
            value={kpis?.created_period ?? '-'}
            subtitle={periodLabel}
            pctChange={pct?.created_period}
            changeDirection="up-good"
            onClick={() => navigate('/executive')}
          />
          <KpiCard
            label="Closed (Period)"
            value={kpis?.closed_period ?? '-'}
            subtitle={periodLabel}
            pctChange={pct?.closed_period}
            changeDirection="up-good"
            onClick={() => navigate('/executive')}
          />
          <KpiCard
            label="Net Flow (Period)"
            value={netFlowPeriodStr}
            subtitle={periodLabel}
            colorClass={netFlowPeriod <= 0 ? 'border-green-500/30' : 'border-red-500/30'}
            onClick={() => navigate('/executive')}
          />
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Created vs Closed Trend */}
        <ChartCard title={`Created vs Closed per ${charts?.volume_granularity === 'day' ? 'Day' : charts?.volume_granularity === 'month' ? 'Month' : 'Week'}`} exportData={charts?.volume_trend} exportFilename="volume_trend">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.volume_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, color: '#9ca3af' }} />
              <Bar dataKey="created" name="Created" fill={BRAND.primary} radius={[2, 2, 0, 0]} />
              <Bar dataKey="closed" name="Closed" fill="#34D399" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* New Tickets Per Day */}
        <ChartCard title="New Tickets Per Day" exportData={charts?.daily_new_tickets} exportFilename="daily_new_tickets">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.daily_new_tickets || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#6b7280' }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: '#6b7280' }} allowDecimals={false} />
              <Tooltip
                {...tooltipStyle}
                labelFormatter={(label: string, payload: any[]) => {
                  const day = payload?.[0]?.payload?.day
                  return day ? `${day}, ${label}` : label
                }}
              />
              <Bar dataKey="count" name="New Tickets" fill="#06B6D4" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Ticket Aging */}
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
          <ResponsiveContainer width="100%" height={Math.max(250, workloadData.length * 32)}>
            <BarChart data={workloadData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="technician" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={100} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {workloadData.map((entry: any, i: number) => {
                  const color = entry.count <= avgLoad ? '#34D399' :
                    entry.count <= avgLoad * 1.5 ? '#FBBF24' : '#F87171'
                  return <Cell key={i} fill={color} />
                })}
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
              <Bar dataKey="count" fill={BRAND.primary} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Status Distribution (horizontal bar instead of donut) */}
        <ChartCard title="Open Tickets by Status" exportData={charts?.status_distribution} exportFilename="status_distribution">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={charts?.status_distribution || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="status" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={120} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {(charts?.status_distribution || []).map((_: any, i: number) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Open Tickets by Priority */}
        <ChartCard title="Open Tickets by Priority" exportData={charts?.priority_distribution} exportFilename="priority_distribution">
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

        {/* Category Distribution */}
        <ChartCard title="Open Tickets by Category" exportData={charts?.category_distribution} exportFilename="category_distribution">
          <ResponsiveContainer width="100%" height={Math.max(250, (charts?.category_distribution?.length || 0) * 28)}>
            <BarChart data={charts?.category_distribution || []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis dataKey="category" type="category" tick={{ fontSize: 11, fill: '#9ca3af' }} width={120} />
              <Tooltip {...tooltipStyle} />
              <Bar dataKey="count" fill="#8B5CF6" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Subcategory Distribution (treemap: handles many items in a fixed area) */}
        <ChartCard title="Open Tickets by Subcategory" exportData={charts?.subcategory_distribution} exportFilename="subcategory_distribution">
          <ResponsiveContainer width="100%" height={350}>
            <Treemap
              data={(charts?.subcategory_distribution || []).map((d: any) => ({
                name: d.subcategory,
                count: d.count,
              }))}
              dataKey="count"
              stroke="#0a0a0a"
              content={<SubcategoryTreemapTile />}
            >
              <Tooltip
                {...tooltipStyle}
                formatter={(value: any) => [value, 'Tickets']}
              />
            </Treemap>
          </ResponsiveContainer>
        </ChartCard>

        {/* SLA Compliance Trend */}
        <ChartCard title="SLA Compliance Trend" exportData={charts?.sla_trend} exportFilename="sla_trend" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={charts?.sla_trend || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#6b7280' }} />
              <YAxis domain={[50, 100]} tick={{ fontSize: 10, fill: '#6b7280' }} tickFormatter={(v: number) => `${v}%`} />
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
