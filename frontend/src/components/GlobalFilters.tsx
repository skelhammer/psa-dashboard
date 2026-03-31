import { useState, useEffect } from 'react'
import { useFilterContext } from '../context/FilterContext'
import { useFilters } from '../api/hooks'
import { DATE_RANGE_OPTIONS } from '../utils/constants'
import { X, ChevronDown } from 'lucide-react'
import clsx from 'clsx'

const selectClass =
  'bg-white/[0.05] border border-white/[0.1] rounded-lg pl-2.5 pr-6 py-1.5 text-xs text-gray-300 focus:border-brand-primary/50 focus:ring-1 focus:ring-brand-primary/20 focus:outline-none appearance-none transition-all duration-150 hover:bg-white/[0.08] hover:border-white/[0.15]'

const dateInputClass =
  'bg-white/[0.05] border border-white/[0.1] rounded-lg px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-primary/50 focus:ring-1 focus:ring-brand-primary/20 focus:outline-none transition-all duration-150 hover:bg-white/[0.08] hover:border-white/[0.15] [color-scheme:dark]'

export default function GlobalFilters() {
  const { filters, setFilter, setFilters, toggleCorp, resetFilters } = useFilterContext()
  const { data } = useFilters()

  // Local state for date inputs; only committed to filter context on blur
  const [localFrom, setLocalFrom] = useState(filters.dateFrom)
  const [localTo, setLocalTo] = useState(filters.dateTo)

  // Sync local state when filters change externally (e.g. reset, preset change)
  useEffect(() => { setLocalFrom(filters.dateFrom) }, [filters.dateFrom])
  useEffect(() => { setLocalTo(filters.dateTo) }, [filters.dateTo])

  const handlePresetChange = (value: string) => {
    if (value !== 'custom') {
      setFilters({ dateRange: value, dateFrom: '', dateTo: '' })
      setLocalFrom('')
      setLocalTo('')
    } else {
      setFilter('dateRange', value)
    }
  }

  const commitDateFrom = (value: string) => {
    if (!value) return
    setFilters({ dateFrom: value, dateRange: 'custom' })
  }

  const commitDateTo = (value: string) => {
    if (!value) return
    setFilters({ dateTo: value, dateRange: 'custom' })
  }

  const displayFrom = localFrom || ''
  const displayTo = localTo || ''

  const hasActiveFilters = filters.clientId || filters.technicianId || filters.priority || filters.techGroup || filters.status || filters.dateRange === 'custom' || filters.provider || filters.showCorp

  const providers = data?.providers || []
  const showProviderToggle = providers.length > 1

  return (
    <div className="flex items-center gap-2.5 flex-wrap rounded-xl bg-white/[0.02] border border-white/[0.06] px-4 py-3">
      {/* Provider toggle (only shown when multiple providers are configured) */}
      {showProviderToggle && (
        <>
          <div className="inline-flex items-center bg-white/[0.04] rounded-lg border border-white/[0.08] p-0.5">
            <button
              onClick={() => setFilter('provider', '')}
              className={clsx(
                'px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150',
                !filters.provider
                  ? 'bg-blue-500/20 text-blue-300 shadow-sm'
                  : 'text-gray-500 hover:text-gray-300'
              )}
            >
              All
            </button>
            {providers.map((p: { name: string; label: string }) => (
              <button
                key={p.name}
                onClick={() => setFilter('provider', p.name)}
                className={clsx(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150',
                  filters.provider === p.name
                    ? p.name === 'zendesk'
                      ? 'bg-orange-500/20 text-orange-300 shadow-sm'
                      : 'bg-blue-500/20 text-blue-300 shadow-sm'
                    : 'text-gray-500 hover:text-gray-300'
                )}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="w-px h-5 bg-white/[0.08] mx-1" />

          {/* Corp toggle (only when Zendesk data is visible) */}
          {(filters.provider === 'zendesk' || !filters.provider) && (
            <button
              onClick={toggleCorp}
              className="inline-flex items-center gap-2 group"
              title={filters.showCorp ? 'Corp tickets included (click to hide)' : 'Corp tickets hidden (click to show)'}
            >
              <div className={clsx(
                'relative w-7 h-4 rounded-full transition-colors duration-200',
                filters.showCorp ? 'bg-purple-500' : 'bg-white/[0.12]'
              )}>
                <div className={clsx(
                  'absolute top-0.5 left-0.5 w-3 h-3 rounded-full bg-white transition-transform duration-200',
                  filters.showCorp && 'translate-x-3'
                )} />
              </div>
              <span className={clsx(
                'text-xs font-medium transition-colors duration-150',
                filters.showCorp ? 'text-purple-300' : 'text-gray-500 group-hover:text-gray-300'
              )}>
                Corp
              </span>
            </button>
          )}

          <div className="w-px h-5 bg-white/[0.08] mx-1" />
        </>
      )}

      {/* Date filters */}
      <div className="relative inline-flex">
        <select value={filters.dateRange} onChange={e => handlePresetChange(e.target.value)} className={selectClass}>
          {DATE_RANGE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>

      <input type="date" value={displayFrom}
        onChange={e => setLocalFrom(e.target.value)}
        onBlur={() => commitDateFrom(localFrom)}
        className={dateInputClass} />
      <span className="text-[10px] text-gray-600 font-medium uppercase">to</span>
      <input type="date" value={displayTo}
        onChange={e => setLocalTo(e.target.value)}
        onBlur={() => commitDateTo(localTo)}
        className={dateInputClass} />

      <div className="w-px h-5 bg-white/[0.08] mx-1" />

      {/* Categorical filters */}
      <div className="relative inline-flex">
        <select value={filters.clientId} onChange={e => setFilter('clientId', e.target.value)} className={selectClass}>
          <option value="">All Clients</option>
          {data?.clients?.map((c: any) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>

      <div className="relative inline-flex">
        <select value={filters.technicianId} onChange={e => setFilter('technicianId', e.target.value)} className={selectClass}>
          <option value="">All Technicians</option>
          {data?.technicians?.map((t: any) => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>

      <div className="relative inline-flex">
        <select value={filters.priority} onChange={e => setFilter('priority', e.target.value)} className={selectClass}>
          <option value="">All Priorities</option>
          {data?.priorities?.map((p: string) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>

      <div className="relative inline-flex">
        <select value={filters.techGroup} onChange={e => setFilter('techGroup', e.target.value)} className={selectClass}>
          <option value="">All Groups</option>
          {data?.groups?.map((g: string) => (
            <option key={g} value={g}>{g}</option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>

      {hasActiveFilters && (
        <button
          onClick={resetFilters}
          className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-red-400 transition-colors duration-150 ml-1"
        >
          <X size={12} />
          Clear
        </button>
      )}
    </div>
  )
}
