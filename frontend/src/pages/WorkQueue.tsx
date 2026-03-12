import { useState } from 'react'
import { useWorkQueue, useFilters } from '../api/hooks'
import TicketTable from '../components/TicketTable'

export default function WorkQueue() {
  const [techId, setTechId] = useState('')
  const [priority, setPriority] = useState('')
  const [clientId, setClientId] = useState('')
  const [unassignedOnly, setUnassignedOnly] = useState(false)

  const params: Record<string, string> = {}
  if (techId) params.technician_id = techId
  if (priority) params.priority = priority
  if (clientId) params.client_id = clientId
  if (unassignedOnly) params.unassigned_only = 'true'

  const { data, isLoading } = useWorkQueue(params)
  const { data: filters } = useFilters()

  const selectClass =
    'bg-gray-800 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-gold/50 focus:outline-none'

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold">Work Queue</h2>
        <p className="text-sm text-gray-500 mt-1">
          Prioritized by SLA urgency, then priority, then age. Pick from the top.
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <select value={techId} onChange={e => setTechId(e.target.value)} className={selectClass}>
          <option value="">All Technicians</option>
          {filters?.technicians?.map((t: any) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>

        <select value={clientId} onChange={e => setClientId(e.target.value)} className={selectClass}>
          <option value="">All Clients</option>
          {filters?.clients?.map((c: any) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>

        <select value={priority} onChange={e => setPriority(e.target.value)} className={selectClass}>
          <option value="">All Priorities</option>
          {filters?.priorities?.map((p: string) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        <label className="flex items-center gap-2 text-xs text-gray-400">
          <input
            type="checkbox"
            checked={unassignedOnly}
            onChange={e => setUnassignedOnly(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800 text-brand-gold focus:ring-brand-gold/50"
          />
          Unassigned only
        </label>

        {data?.count !== undefined && (
          <span className="text-xs text-gray-500 ml-auto">
            {data.count} tickets
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="text-gray-500">Loading queue...</div>
      ) : (
        <TicketTable
          tickets={data?.tickets || []}
          showRank
          showScore
          emptyMessage="Queue is empty. All caught up!"
        />
      )}
    </div>
  )
}
