import { useState } from 'react'
import { useManageToZero, useMtzDrilldown } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import { zeroTargetColor, zeroTargetTextColor } from '../utils/formatting'
import TicketTable from '../components/TicketTable'
import clsx from 'clsx'

const CARDS = [
  { key: 'unassigned', label: 'Unassigned', desc: 'No technician assigned' },
  { key: 'no_first_response', label: 'No First Response', desc: 'Customer waiting for initial reply' },
  { key: 'awaiting_tech_reply', label: 'Awaiting Tech Reply', desc: 'Customer replied, tech has not' },
  { key: 'stale', label: 'Stale Tickets', desc: 'No update in 3+ days' },
  { key: 'sla_breaching_soon', label: 'SLA Breaching Soon', desc: 'Within 30 minutes of breach' },
  { key: 'sla_violated', label: 'SLA Violated', desc: 'Already past SLA deadline' },
  { key: 'unresolved_billing_flags', label: 'Billing Flags', desc: 'Unbilled/underbilled tickets' },
]

export default function ManageToZero() {
  const { toParams } = useFilterContext()
  const providerParams = (() => {
    const p = toParams()
    // MTZ only needs the provider and corp filters, not date/other filters
    const result: Record<string, string> = {}
    if (p.provider) result.provider = p.provider
    if (p.hide_corp) result.hide_corp = p.hide_corp
    return result
  })()
  const { data, isLoading } = useManageToZero(providerParams)
  const [activeCard, setActiveCard] = useState<string | null>(null)
  const { data: drilldown, isLoading: drillLoading } = useMtzDrilldown(activeCard, providerParams)

  if (isLoading && !data) {
    return <div className="text-gray-500">Loading...</div>
  }

  const cards = data?.cards || {}

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header">
        <h2 className="text-xl font-bold">Manage to Zero</h2>
        <p className="text-sm text-gray-500 mt-1">Drive all numbers to zero by end of day.</p>
      </div>

      {/* Zero-target cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        {CARDS.map(card => {
          const count = cards[card.key] ?? 0
          const isActive = activeCard === card.key
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
              <p className={clsx('text-3xl font-bold tabular-nums', zeroTargetTextColor(count))}>
                {count}
              </p>
              <p className="text-xs font-medium text-gray-300 mt-1">{card.label}</p>
              <p className="text-xs text-gray-600 mt-0.5">{card.desc}</p>
            </button>
          )
        })}
      </div>

      {/* Drill-down */}
      {activeCard && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold">
              {CARDS.find(c => c.key === activeCard)?.label} Tickets
            </h3>
            {drilldown?.count !== undefined && (
              <span className="text-xs bg-zinc-800 px-2 py-0.5 rounded-full text-gray-400">
                {drilldown.count} tickets
              </span>
            )}
          </div>

          {drillLoading ? (
            <div className="text-gray-500">Loading tickets...</div>
          ) : (
            <TicketTable
              tickets={drilldown?.tickets || []}
              emptyMessage="No tickets in this category. Nice work!"
            />
          )}
        </div>
      )}
    </div>
  )
}
