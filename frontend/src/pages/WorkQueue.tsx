import { useState } from 'react'
import { useWorkQueue } from '../api/hooks'
import { useFilterContext } from '../context/FilterContext'
import GlobalFilters from '../components/GlobalFilters'
import TicketTable from '../components/TicketTable'
import ExportButtons from '../components/ExportButtons'

export default function WorkQueue() {
  const { toParams } = useFilterContext()
  const [unassignedOnly, setUnassignedOnly] = useState(false)

  const params = toParams()
  if (unassignedOnly) params.unassigned_only = 'true'

  const { data, isLoading } = useWorkQueue(params)

  const queueCsvData = (data?.tickets || []).map((t: any) => ({
    rank: t.rank,
    display_id: t.display_id,
    subject: t.subject,
    client_name: t.client_name,
    technician_name: t.technician_name || 'Unassigned',
    priority: t.priority,
    status: t.status,
    created_time: t.created_time,
    worklog_hours: t.worklog_hours,
    score: t.score,
  }))

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold">Work Queue</h2>
          <p className="text-sm text-gray-500 mt-1">
            Prioritized by SLA urgency, then priority, then age. Pick from the top.
          </p>
        </div>
        <ExportButtons
          csvData={queueCsvData}
          csvFilename="work_queue"
          csvColumns={[
            { key: 'rank', label: 'Rank' },
            { key: 'display_id', label: 'ID' },
            { key: 'subject', label: 'Subject' },
            { key: 'client_name', label: 'Client' },
            { key: 'technician_name', label: 'Tech' },
            { key: 'priority', label: 'Priority' },
            { key: 'status', label: 'Status' },
            { key: 'created_time', label: 'Created' },
            { key: 'worklog_hours', label: 'Time (hrs)' },
            { key: 'score', label: 'Score' },
          ]}
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
