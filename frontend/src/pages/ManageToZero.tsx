import { useState } from 'react'
import { useManageToZero, useMtzDrilldown } from '../api/hooks'
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
  const { data, isLoading } = useManageToZero()
  const [activeCard, setActiveCard] = useState<string | null>(null)
  const { data: drilldown, isLoading: drillLoading } = useMtzDrilldown(activeCard)

  if (isLoading) {
    return <div className="text-gray-500">Loading...</div>
  }

  const cards = data?.cards || {}

  return (
    <div className="space-y-6">
      <div>
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
                'rounded-lg p-4 text-left transition-all',
                isActive
                  ? 'ring-2 ring-brand-gold border border-brand-gold/40 bg-brand-gold/5'
                  : 'border border-gray-800 bg-gray-900 hover:border-gray-700'
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
              <span className="text-xs bg-gray-800 px-2 py-0.5 rounded-full text-gray-400">
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
