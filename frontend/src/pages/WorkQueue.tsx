import { useState } from 'react'
import { useWorkQueue } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import GlobalFilters from '../components/GlobalFilters'
import TicketTable from '../components/TicketTable'

export default function WorkQueue() {
  const { toParams } = useFilterContext()
  const [unassignedOnly, setUnassignedOnly] = useState(false)

  const params = toParams()
  if (unassignedOnly) params.unassigned_only = 'true'

  const { data, isLoading } = useWorkQueue(params)

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold">Work Queue</h2>
        <p className="text-sm text-gray-500 mt-1">
          Prioritized by SLA urgency, then priority, then age. Pick from the top.
        </p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <GlobalFilters />

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
