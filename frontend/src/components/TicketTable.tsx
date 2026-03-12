import { useState } from 'react'
import clsx from 'clsx'
import { PRIORITY_COLORS, STATUS_COLORS } from '../utils/constants'
import { formatAge, formatWorklogHours } from '../utils/formatting'
import SlaCountdown from './SlaCountdown'

interface Ticket {
  id: string
  display_id: string
  subject: string
  client_name: string
  technician_name: string | null
  status: string
  priority: string
  created_time: string
  updated_time: string
  first_response_due?: string | null
  first_response_violated?: boolean | null
  resolution_due?: string | null
  resolution_violated?: boolean | null
  worklog_minutes: number
  url?: string
  rank?: number
  score?: number
}

interface Column {
  key: string
  label: string
  sortable?: boolean
  render?: (ticket: Ticket) => React.ReactNode
}

interface TicketTableProps {
  tickets: Ticket[]
  showRank?: boolean
  showScore?: boolean
  emptyMessage?: string
}

const defaultColumns: Column[] = [
  {
    key: 'display_id',
    label: 'ID',
    sortable: true,
    render: (t) => (
      <a
        href={t.url || '#'}
        target="_blank"
        rel="noopener noreferrer"
        className="text-brand-gold hover:text-brand-gold-light font-mono text-xs"
      >
        {t.display_id}
      </a>
    ),
  },
  { key: 'subject', label: 'Subject', sortable: true },
  { key: 'client_name', label: 'Client', sortable: true },
  {
    key: 'technician_name',
    label: 'Tech',
    sortable: true,
    render: (t) => (
      <span className={clsx(!t.technician_name && 'text-red-400 font-medium')}>
        {t.technician_name || 'Unassigned'}
      </span>
    ),
  },
  {
    key: 'priority',
    label: 'Priority',
    sortable: true,
    render: (t) => (
      <span
        className={clsx(
          'px-2 py-0.5 rounded-full text-xs font-medium border',
          PRIORITY_COLORS[t.priority] || 'text-gray-400'
        )}
      >
        {t.priority}
      </span>
    ),
  },
  {
    key: 'status',
    label: 'Status',
    sortable: true,
    render: (t) => (
      <span className={clsx('text-xs', STATUS_COLORS[t.status] || 'text-gray-400')}>
        {t.status}
      </span>
    ),
  },
  {
    key: 'age',
    label: 'Age',
    sortable: true,
    render: (t) => <span className="text-xs tabular-nums">{formatAge(t.created_time)}</span>,
  },
  {
    key: 'sla',
    label: 'SLA',
    sortable: false,
    render: (t) => <SlaCountdown ticket={t} />,
  },
  {
    key: 'worklog_minutes',
    label: 'Time',
    sortable: true,
    render: (t) => (
      <span className="text-xs tabular-nums text-gray-400">
        {t.worklog_minutes > 0 ? formatWorklogHours(t.worklog_minutes) : '-'}
      </span>
    ),
  },
]

type SortDir = 'asc' | 'desc'

const PRIORITY_WEIGHT: Record<string, number> = {
  Critical: 5, Urgent: 5, High: 4, Medium: 3, Low: 2, 'Very Low': 1,
}

export default function TicketTable({ tickets, showRank, showScore, emptyMessage }: TicketTableProps) {
  const [sortKey, setSortKey] = useState<string>('priority')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'priority' ? 'desc' : 'asc')
    }
  }

  const sorted = [...tickets].sort((a, b) => {
    let aVal: any, bVal: any

    if (sortKey === 'priority') {
      aVal = PRIORITY_WEIGHT[a.priority] || 0
      bVal = PRIORITY_WEIGHT[b.priority] || 0
    } else if (sortKey === 'age') {
      aVal = new Date(a.created_time).getTime()
      bVal = new Date(b.created_time).getTime()
    } else {
      aVal = (a as any)[sortKey] ?? ''
      bVal = (b as any)[sortKey] ?? ''
    }

    if (typeof aVal === 'string') {
      const cmp = aVal.localeCompare(bVal)
      return sortDir === 'asc' ? cmp : -cmp
    }
    return sortDir === 'asc' ? aVal - bVal : bVal - aVal
  })

  if (!tickets.length) {
    return (
      <div className="card text-center py-12 text-gray-500">
        {emptyMessage || 'No tickets found'}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-900/80 border-b border-gray-800">
            {showRank && <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500">#</th>}
            {defaultColumns.map(col => (
              <th
                key={col.key}
                onClick={() => col.sortable && handleSort(col.key)}
                className={clsx(
                  'px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap',
                  col.sortable && 'cursor-pointer hover:text-gray-300 select-none'
                )}
              >
                {col.label}
                {sortKey === col.key && (
                  <span className="ml-1 text-brand-gold">{sortDir === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
            ))}
            {showScore && <th className="px-3 py-2.5 text-left text-xs font-medium text-gray-500">Score</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/50">
          {sorted.map((ticket, i) => (
            <tr
              key={ticket.id}
              className="hover:bg-gray-800/30 transition-colors"
            >
              {showRank && (
                <td className="px-3 py-2.5 text-xs text-gray-500 font-mono">
                  {ticket.rank ?? i + 1}
                </td>
              )}
              {defaultColumns.map(col => (
                <td key={col.key} className="px-3 py-2.5 max-w-[250px] truncate">
                  {col.render ? col.render(ticket) : (ticket as any)[col.key]}
                </td>
              ))}
              {showScore && (
                <td className="px-3 py-2.5 text-xs text-gray-500 font-mono tabular-nums">
                  {ticket.score?.toFixed(0)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
