import { useState } from 'react'
import { useBillingFlags, useBillingSummary, useResolveFlag, useFilters } from '../api/hooks'
import KpiCard from '../components/KpiCard'
import clsx from 'clsx'
import { PRIORITY_COLORS } from '../utils/constants'

const FLAG_TYPE_COLORS: Record<string, string> = {
  MISSING_WORKLOG: 'text-red-400 bg-red-400/10 border-red-400/30',
  ZERO_TIME: 'text-orange-400 bg-orange-400/10 border-orange-400/30',
  LOW_TIME: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30',
  MANUAL: 'text-purple-400 bg-purple-400/10 border-purple-400/30',
}

export default function BillingAudit() {
  const [showResolved, setShowResolved] = useState(false)
  const [flagType, setFlagType] = useState('')
  const [resolveId, setResolveId] = useState<number | null>(null)
  const [resolveNote, setResolveNote] = useState('')

  const params: Record<string, string> = {}
  if (showResolved) params.resolved = 'true'
  if (flagType) params.flag_type = flagType

  const { data: flags, isLoading } = useBillingFlags(params)
  const { data: summary } = useBillingSummary()
  const resolveMutation = useResolveFlag()
  const { data: filterOpts } = useFilters()

  const selectClass =
    'bg-gray-800 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-gold/50 focus:outline-none'

  const handleResolve = (flagId: number) => {
    if (!resolveNote.trim()) return
    resolveMutation.mutate({
      flagId,
      resolved_by: 'Admin',
      resolution_note: resolveNote,
    }, {
      onSuccess: () => {
        setResolveId(null)
        setResolveNote('')
      },
    })
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Billing Audit</h2>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard
          label="Unresolved Flags"
          value={summary?.kpis?.unresolved_flags ?? '-'}
          colorClass={summary?.kpis?.unresolved_flags > 0 ? 'border-red-500/30' : 'border-green-500/30'}
        />
        <KpiCard label="Resolved This Week" value={summary?.kpis?.resolved_this_week ?? '-'} />
        <KpiCard label="Resolved This Month" value={summary?.kpis?.resolved_this_month ?? '-'} />
        <KpiCard
          label="Billable Clients"
          value={summary?.clients?.length ?? '-'}
        />
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex items-center gap-2 text-xs text-gray-400">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={e => setShowResolved(e.target.checked)}
            className="rounded border-gray-600 bg-gray-800"
          />
          Show resolved
        </label>

        <select value={flagType} onChange={e => setFlagType(e.target.value)} className={selectClass}>
          <option value="">All Flag Types</option>
          <option value="MISSING_WORKLOG">Missing Worklog</option>
          <option value="ZERO_TIME">Zero Time</option>
          <option value="LOW_TIME">Low Time</option>
        </select>

        <span className="text-xs text-gray-500 ml-auto">{flags?.count ?? 0} flags</span>
      </div>

      {/* Flags Table */}
      {isLoading ? (
        <div className="text-gray-500">Loading...</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-900/80 border-b border-gray-800">
                {['Flag', 'Ticket', 'Subject', 'Client', 'Tech', 'Priority', 'Time', 'Reason', 'Action'].map(h => (
                  <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50">
              {(flags?.flags || []).map((flag: any) => (
                <tr key={flag.id} className="hover:bg-gray-800/30 transition-colors">
                  <td className="px-3 py-2.5">
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium border', FLAG_TYPE_COLORS[flag.flag_type] || '')}>
                      {flag.flag_type.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <a href={flag.url} target="_blank" rel="noopener noreferrer" className="text-brand-gold hover:text-brand-gold-light font-mono text-xs">
                      {flag.display_id}
                    </a>
                  </td>
                  <td className="px-3 py-2.5 max-w-[200px] truncate">{flag.subject}</td>
                  <td className="px-3 py-2.5 text-xs">{flag.client_name}</td>
                  <td className="px-3 py-2.5 text-xs">{flag.technician_name || 'Unassigned'}</td>
                  <td className="px-3 py-2.5">
                    <span className={clsx('px-2 py-0.5 rounded-full text-xs font-medium border', PRIORITY_COLORS[flag.priority] || '')}>
                      {flag.priority}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-xs tabular-nums text-gray-400">
                    {flag.worklog_minutes > 0 ? `${(flag.worklog_minutes / 60).toFixed(1)}h` : '-'}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-gray-400 max-w-[200px] truncate">{flag.flag_reason}</td>
                  <td className="px-3 py-2.5">
                    {!flag.resolved && (
                      resolveId === flag.id ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="text"
                            value={resolveNote}
                            onChange={e => setResolveNote(e.target.value)}
                            placeholder="Resolution note..."
                            className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs w-40"
                            onKeyDown={e => e.key === 'Enter' && handleResolve(flag.id)}
                          />
                          <button
                            onClick={() => handleResolve(flag.id)}
                            className="text-xs text-green-400 hover:text-green-300"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => { setResolveId(null); setResolveNote('') }}
                            className="text-xs text-gray-500 hover:text-gray-300"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setResolveId(flag.id)}
                          className="text-xs text-brand-gold hover:text-brand-gold-light"
                        >
                          Resolve
                        </button>
                      )
                    )}
                    {flag.resolved && (
                      <span className="text-xs text-green-400/60">Resolved</span>
                    )}
                  </td>
                </tr>
              ))}
              {!flags?.flags?.length && (
                <tr>
                  <td colSpan={9} className="px-3 py-8 text-center text-gray-500">
                    No billing flags. All billable tickets are properly logged.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Billable Clients Summary */}
      {summary?.clients?.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-lg font-semibold">Billable Clients</h3>
          <div className="overflow-x-auto rounded-lg border border-gray-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-900/80 border-b border-gray-800">
                  {['Client', 'Type', 'Source', 'Tickets (Mo)', 'With Time', 'Missing', 'Missing %', 'Hours', 'Flags'].map(h => (
                    <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {summary.clients.map((c: any) => (
                  <tr key={c.client_id} className="hover:bg-gray-800/30">
                    <td className="px-3 py-2.5 font-medium">{c.name}</td>
                    <td className="px-3 py-2.5 text-xs">{c.billing_type}</td>
                    <td className="px-3 py-2.5">
                      <span className={clsx(
                        'text-xs px-1.5 py-0.5 rounded',
                        c.auto_detected ? 'bg-blue-400/10 text-blue-400' : 'bg-purple-400/10 text-purple-400'
                      )}>
                        {c.auto_detected ? 'Contract' : 'Manual'}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">{c.total_tickets_month}</td>
                    <td className="px-3 py-2.5 tabular-nums text-green-400">{c.tickets_with_time}</td>
                    <td className="px-3 py-2.5 tabular-nums">
                      <span className={c.tickets_missing_time > 0 ? 'text-red-400' : ''}>{c.tickets_missing_time}</span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      <span className={c.missing_pct > 0 ? 'text-red-400 font-medium' : 'text-green-400'}>{c.missing_pct}%</span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">{c.billed_hours}h</td>
                    <td className="px-3 py-2.5 tabular-nums">
                      <span className={c.unresolved_flags > 0 ? 'text-red-400 font-medium' : ''}>{c.unresolved_flags}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
