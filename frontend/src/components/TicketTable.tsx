import { useState } from 'react'
import clsx from 'clsx'
import { PRIORITY_COLORS, STATUS_COLORS } from '../utils/constants'
import { formatAge, formatWorklogHours } from '../utils/formatting'
import { ChevronUp, ChevronDown, Inbox, CircleDot } from 'lucide-react'
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
  first_response_time?: string | null
  first_response_violated?: boolean | null
  resolution_due?: string | null
  resolution_violated?: boolean | null
  worklog_hours: number
  provider?: string | null
  url?: string
  rank?: number
  score?: number
  last_responder_type?: string | null
  reopened?: boolean
  category?: string | null
  tech_group_name?: string | null
  conversation_count?: number
  tech_reply_count?: number
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
  showLastResponder?: boolean
  showCategory?: boolean
  showTechGroup?: boolean
  emptyMessage?: string
  defaultSortKey?: string
  defaultSortDir?: 'asc' | 'desc'
}

function getSlaSortValue(ticket: Ticket): number {
  if (ticket.first_response_violated || ticket.resolution_violated) return -Infinity
  const frApplies = ticket.first_response_due && !ticket.first_response_time
  const frDue = frApplies ? new Date(ticket.first_response_due!).getTime() : Infinity
  const resDue = ticket.resolution_due ? new Date(ticket.resolution_due).getTime() : Infinity
  const nearest = Math.min(frDue, resDue)
  return nearest === Infinity ? Infinity : nearest
}

const defaultColumns: Column[] = [
  {
    key: 'display_id',
    label: 'ID',
    sortable: true,
    render: (t) => (
      <span className="inline-flex items-center gap-1.5">
        {t.provider && (
          <span className={clsx(
            'px-1 py-0.5 rounded text-[9px] font-semibold uppercase leading-none',
            t.provider === 'zendesk' ? 'bg-orange-500/15 text-orange-400' : 'bg-blue-500/15 text-blue-400'
          )}>
            {t.provider === 'zendesk' ? 'ZD' : 'SO'}
          </span>
        )}
        <a
          href={t.url || '#'}
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand-primary-light hover:text-brand-primary hover:underline font-mono text-xs transition-colors"
        >
          {t.display_id}
        </a>
      </span>
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
      <span className={clsx('text-xs font-medium', STATUS_COLORS[t.status] || 'text-gray-400')}>
        {t.status}
      </span>
    ),
  },
  {
    key: 'age',
    label: 'Age',
    sortable: true,
    render: (t) => <span className="text-xs tabular-nums text-gray-400">{formatAge(t.created_time)}</span>,
  },
  {
    key: 'sla',
    label: 'SLA',
    sortable: true,
    render: (t) => <SlaCountdown ticket={t} />,
  },
  {
    key: 'worklog_hours',
    label: 'Time',
    sortable: true,
    render: (t) => (
      <span className="text-xs tabular-nums text-gray-400">
        {t.worklog_hours > 0 ? formatWorklogHours(t.worklog_hours) : '-'}
      </span>
    ),
  },
]

// Optional columns
const lastResponderColumn: Column = {
  key: 'last_responder_type',
  label: 'Ball',
  sortable: true,
  render: (t) => {
    if (t.last_responder_type === 'requester') {
      return (
        <span className="inline-flex items-center gap-1 text-xs text-orange-400" title="Customer waiting for tech reply">
          <CircleDot size={12} className="fill-orange-400/30" />
          <span className="hidden xl:inline">Cust</span>
        </span>
      )
    }
    if (t.last_responder_type === 'tech') {
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-400" title="Tech replied, waiting on customer">
          <CircleDot size={12} className="fill-green-400/30" />
          <span className="hidden xl:inline">Tech</span>
        </span>
      )
    }
    return <span className="text-xs text-gray-600">-</span>
  },
}

const categoryColumn: Column = {
  key: 'category',
  label: 'Category',
  sortable: true,
  render: (t) => (
    <span className="text-xs text-gray-400">{t.category || '-'}</span>
  ),
}

const techGroupColumn: Column = {
  key: 'tech_group_name',
  label: 'Group',
  sortable: true,
  render: (t) => (
    <span className="text-xs text-gray-400">{t.tech_group_name || '-'}</span>
  ),
}

type SortDir = 'asc' | 'desc'

const PRIORITY_WEIGHT: Record<string, number> = {
  Critical: 5, Urgent: 5, High: 4, Medium: 3, Low: 2, 'Very Low': 1,
}

export default function TicketTable({ tickets, showRank, showScore, showLastResponder, showCategory, showTechGroup, emptyMessage, defaultSortKey, defaultSortDir }: TicketTableProps) {
  const [sortKey, setSortKey] = useState<string>(defaultSortKey || 'priority')
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir || 'desc')

  // Build columns list based on props
  const columns: Column[] = [...defaultColumns]
  if (showLastResponder) {
    // Insert after status column
    const statusIdx = columns.findIndex(c => c.key === 'status')
    columns.splice(statusIdx + 1, 0, lastResponderColumn)
  }
  if (showTechGroup) {
    // Insert after tech column
    const techIdx = columns.findIndex(c => c.key === 'technician_name')
    columns.splice(techIdx + 1, 0, techGroupColumn)
  }
  if (showCategory) {
    // Insert before age column
    const ageIdx = columns.findIndex(c => c.key === 'age')
    columns.splice(ageIdx, 0, categoryColumn)
  }

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
    } else if (sortKey === 'sla') {
      aVal = getSlaSortValue(a)
      bVal = getSlaSortValue(b)
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
      <div className="card text-center py-16">
        <Inbox size={32} className="mx-auto text-gray-600 mb-3" />
        <p className="text-gray-500 text-sm">{emptyMessage || 'No tickets found'}</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/[0.08] shadow-lg shadow-black/20">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[#111113] border-b border-white/[0.08]">
            {showRank && <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider">#</th>}
            {columns.map(col => (
              <th
                key={col.key}
                onClick={() => col.sortable && handleSort(col.key)}
                className={clsx(
                  'px-4 py-3 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap',
                  col.sortable && 'cursor-pointer hover:text-gray-300 select-none transition-colors'
                )}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {sortKey === col.key && (
                    sortDir === 'asc'
                      ? <ChevronUp size={12} className="text-brand-primary" />
                      : <ChevronDown size={12} className="text-brand-primary" />
                  )}
                </span>
              </th>
            ))}
            {showScore && <th className="px-4 py-3 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wider">Score</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.04]">
          {sorted.map((ticket, i) => {
            const score = ticket.score ?? 0
            const urgencyBand = score >= 1000
              ? 'border-l-2 border-l-red-500/60 bg-red-500/[0.03]'
              : score >= 500
                ? 'border-l-2 border-l-yellow-500/40 bg-yellow-500/[0.02]'
                : ''

            return (
              <tr
                key={ticket.id}
                className={clsx('hover:bg-white/[0.03] transition-colors', urgencyBand)}
              >
                {showRank && (
                  <td className="px-4 py-3 text-xs text-gray-500 font-mono">
                    {ticket.rank ?? i + 1}
                  </td>
                )}
                {columns.map(col => (
                  <td key={col.key} className={clsx('px-4 py-3', col.key === 'subject' && 'max-w-[250px] truncate')}>
                    {col.render ? col.render(ticket) : (ticket as any)[col.key]}
                  </td>
                ))}
                {showScore && (
                  <td className="px-4 py-3 text-xs font-mono tabular-nums">
                    <span className={clsx(
                      score >= 1000 ? 'text-red-400' :
                      score >= 500 ? 'text-yellow-400' :
                      score >= 200 ? 'text-orange-300' : 'text-gray-500'
                    )}>
                      {score.toFixed(0)}
                    </span>
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
