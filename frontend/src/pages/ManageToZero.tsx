import { useState, useMemo } from 'react'
import { useManageToZero, useMtzDrilldown, useMtzTrends, useFilters } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { zeroTargetColor, zeroTargetTextColor } from '../utils/formatting'
import TicketTable from '../components/TicketTable'
import clsx from 'clsx'
import { TrendingUp, TrendingDown, Minus, RefreshCw } from 'lucide-react'

/* ------------------------------------------------------------------ */
/*  Card definitions                                                  */
/* ------------------------------------------------------------------ */

interface CardDef {
  key: string
  label: string
  desc: string
  sortKey?: string
  sortDir?: 'asc' | 'desc'
  section: 'ops' | 'admin'
}

const CARDS: CardDef[] = [
  { key: 'unassigned', label: 'Unassigned', desc: 'No technician assigned', sortKey: 'priority', sortDir: 'desc', section: 'ops' },
  { key: 'no_first_response', label: 'No First Response', desc: 'Customer waiting for initial reply', sortKey: 'priority', sortDir: 'desc', section: 'ops' },
  { key: 'awaiting_tech_reply', label: 'Awaiting Tech Reply', desc: 'Customer replied, tech has not', sortKey: 'age', sortDir: 'asc', section: 'ops' },
  { key: 'stale', label: 'Stale Tickets', desc: 'No update past threshold (excl. waiting)', sortKey: 'age', sortDir: 'asc', section: 'ops' },
  { key: 'sla_breaching_soon', label: 'SLA Breaching Soon', desc: 'Approaching SLA deadline', sortKey: 'sla', sortDir: 'asc', section: 'ops' },
  { key: 'open_violations', label: 'Open Violations', desc: 'Resolve or escalate past-SLA tickets', sortKey: 'priority', sortDir: 'desc', section: 'ops' },
  { key: 'reopened', label: 'Reopened', desc: 'Quality escapes needing re-attention', sortKey: 'priority', sortDir: 'desc', section: 'ops' },
  { key: 'unresolved_billing_flags', label: 'Billing Flags', desc: 'Unbilled/underbilled tickets', sortKey: 'priority', sortDir: 'desc', section: 'admin' },
]

const OPS_CARDS = CARDS.filter(c => c.section === 'ops')
const ADMIN_CARDS = CARDS.filter(c => c.section === 'admin')

/* ------------------------------------------------------------------ */
/*  Sparkline mini-component                                          */
/* ------------------------------------------------------------------ */

function MiniSparkline({ data }: { data: { count: number }[] }) {
  if (!data || data.length < 2) return null

  const counts = data.map(d => d.count)
  const max = Math.max(...counts, 1)
  const min = Math.min(...counts, 0)
  const range = max - min || 1
  const w = 48
  const h = 16
  const points = counts.map((c, i) => {
    const x = (i / (counts.length - 1)) * w
    const y = h - ((c - min) / range) * h
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={w} height={h} className="opacity-50">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

/* ------------------------------------------------------------------ */
/*  Trend indicator                                                   */
/* ------------------------------------------------------------------ */

function TrendIndicator({ data }: { data?: { count: number }[] }) {
  if (!data || data.length < 2) return null

  const latest = data[data.length - 1].count
  const earlier = data[0].count
  const diff = latest - earlier

  if (diff === 0) return <Minus size={10} className="text-gray-500" />
  if (diff < 0) return <TrendingDown size={10} className="text-green-400" />
  return <TrendingUp size={10} className="text-red-400" />
}

/* ------------------------------------------------------------------ */
/*  Tech breakdown bar                                                */
/* ------------------------------------------------------------------ */

interface Ticket {
  technician_name: string | null
  [key: string]: any
}

function TechBreakdown({ tickets }: { tickets: Ticket[] }) {
  const grouped = useMemo(() => {
    const map: Record<string, number> = {}
    for (const t of tickets) {
      const name = t.technician_name || 'Unassigned'
      map[name] = (map[name] || 0) + 1
    }
    return Object.entries(map)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
  }, [tickets])

  if (grouped.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {grouped.map(([name, count]) => (
        <span
          key={name}
          className={clsx(
            'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border',
            name === 'Unassigned'
              ? 'border-red-500/30 bg-red-500/10 text-red-400'
              : 'border-white/[0.08] bg-white/[0.03] text-gray-300'
          )}
        >
          <span className="font-semibold tabular-nums">{count}</span>
          <span className="text-gray-500">{name}</span>
        </span>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Card grid renderer                                                */
/* ------------------------------------------------------------------ */

function CardGrid({
  cards: cardDefs,
  counts,
  activeCard,
  setActiveCard,
  thresholds,
  trends,
  columns,
}: {
  cards: CardDef[]
  counts: Record<string, number>
  activeCard: string | null
  setActiveCard: (key: string | null) => void
  thresholds: { yellow: number; red: number }
  trends: Record<string, { count: number }[]>
  columns: number
}) {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-4 lg:grid-cols-${columns} gap-3`}>
      {cardDefs.map(card => {
        const count = counts[card.key] ?? 0
        const isActive = activeCard === card.key
        const trendData = trends[card.key]
        return (
          <button
            key={card.key}
            onClick={() => setActiveCard(isActive ? null : card.key)}
            className={clsx(
              'group rounded-xl p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg shadow-black/25',
              isActive
                ? 'ring-2 ring-brand-primary border border-brand-primary/40 bg-brand-primary/5'
                : 'border border-white/[0.08] bg-[#111113] hover:border-white/[0.15]'
            )}
          >
            <div className="flex items-start justify-between">
              <p className={clsx('text-3xl font-bold tabular-nums', zeroTargetTextColor(count, thresholds.yellow, thresholds.red))}>
                {count}
              </p>
              <div className="flex items-center gap-1 mt-1">
                <TrendIndicator data={trendData} />
                <MiniSparkline data={trendData} />
              </div>
            </div>
            <p className="text-xs font-medium text-gray-300 mt-1">{card.label}</p>
            <p className="text-xs text-gray-600 mt-0.5">{card.desc}</p>
          </button>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/*  Main page component                                               */
/* ------------------------------------------------------------------ */

export default function ManageToZero() {
  const { toParams } = useFilterContext()
  const providerParams = (() => {
    const p = toParams()
    const result: Record<string, string> = {}
    if (p.provider) result.provider = p.provider
    if (p.hide_corp) result.hide_corp = p.hide_corp
    return result
  })()
  const { data, isLoading, dataUpdatedAt } = useManageToZero(providerParams)
  const [activeCard, setActiveCard] = useState<string | null>(null)
  const { data: trendsData } = useMtzTrends()
  const { data: filterOptions } = useFilters()

  // Drill-down filters (tech + client)
  const [drillTech, setDrillTech] = useState('')
  const [drillClient, setDrillClient] = useState('')

  const drillParams = useMemo(() => {
    const p: Record<string, string> = { ...providerParams }
    if (drillTech) p.technician_id = drillTech
    if (drillClient) p.client_id = drillClient
    return p
  }, [providerParams, drillTech, drillClient])

  const { data: drilldown, isLoading: drillLoading } = useMtzDrilldown(activeCard, drillParams)

  // Reset drill filters when switching cards
  const handleCardClick = (key: string | null) => {
    if (key !== activeCard) {
      setDrillTech('')
      setDrillClient('')
    }
    setActiveCard(key)
  }

  if (isLoading && !data) {
    return <div className="text-gray-500">Loading...</div>
  }

  const cards = data?.cards || {}
  const thresholds = data?.thresholds || { yellow: 2, red: 5 }
  const trends = trendsData?.trends || {}

  const activeCardDef = CARDS.find(c => c.key === activeCard)
  const lastRefreshed = dataUpdatedAt ? new Date(dataUpdatedAt) : null

  return (
    <div className="space-y-6 animate-slide-up">
      {/* Header */}
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Manage to Zero</h2>
          <p className="text-sm text-gray-500 mt-1">Drive all numbers to zero by end of day.</p>
        </div>
        {lastRefreshed && (
          <div className="flex items-center gap-1.5 text-[11px] text-gray-600">
            <RefreshCw size={10} />
            Updated {lastRefreshed.toLocaleTimeString()}
          </div>
        )}
      </div>

      {/* Operational cards */}
      <CardGrid
        cards={OPS_CARDS}
        counts={cards}
        activeCard={activeCard}
        setActiveCard={handleCardClick}
        thresholds={thresholds}
        trends={trends}
        columns={7}
      />

      {/* Administrative section */}
      {ADMIN_CARDS.length > 0 && (
        <div className="space-y-2">
          <p className="text-[11px] uppercase tracking-wider text-gray-600 font-semibold">Administrative</p>
          <CardGrid
            cards={ADMIN_CARDS}
            counts={cards}
            activeCard={activeCard}
            setActiveCard={handleCardClick}
            thresholds={thresholds}
            trends={trends}
            columns={4}
          />
        </div>
      )}

      {/* Drill-down */}
      {activeCard && activeCardDef && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-lg font-semibold">
              {activeCardDef.label} Tickets
            </h3>
            {drilldown?.count !== undefined && (
              <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded-full text-gray-400">
                {drilldown.count} tickets
              </span>
            )}

            {/* Drill-down filters */}
            <div className="ml-auto flex items-center gap-2">
              {filterOptions?.technicians && (
                <select
                  value={drillTech}
                  onChange={e => setDrillTech(e.target.value)}
                  className="text-xs bg-[#111113] border border-white/[0.08] rounded-lg px-2 py-1.5 text-gray-300 focus:border-brand-primary/50 focus:outline-none"
                >
                  <option value="">All Technicians</option>
                  {filterOptions.technicians.map((t: any) => (
                    <option key={t.id} value={t.id}>
                      {t.first_name} {t.last_name}
                    </option>
                  ))}
                </select>
              )}
              {filterOptions?.clients && (
                <select
                  value={drillClient}
                  onChange={e => setDrillClient(e.target.value)}
                  className="text-xs bg-[#111113] border border-white/[0.08] rounded-lg px-2 py-1.5 text-gray-300 focus:border-brand-primary/50 focus:outline-none"
                >
                  <option value="">All Clients</option>
                  {filterOptions.clients.map((c: any) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Tech breakdown */}
          {drilldown?.tickets && drilldown.tickets.length > 0 && (
            <TechBreakdown tickets={drilldown.tickets} />
          )}

          {drillLoading ? (
            <div className="text-gray-500">Loading tickets...</div>
          ) : (
            <TicketTable
              tickets={drilldown?.tickets || []}
              emptyMessage="No tickets in this category. Nice work!"
              defaultSortKey={activeCardDef.sortKey}
              defaultSortDir={activeCardDef.sortDir}
            />
          )}
        </div>
      )}
    </div>
  )
}
