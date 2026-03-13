import { useFilterContext } from '../context/FilterContext'
import { useFilters, useDateRangeInfo } from '../api/hooks'
import { DATE_RANGE_OPTIONS } from '../utils/constants'
import { X, ChevronDown } from 'lucide-react'

const selectClass =
  'bg-white/[0.05] border border-white/[0.1] rounded-lg pl-2.5 pr-6 py-1.5 text-xs text-gray-300 focus:border-brand-primary/50 focus:ring-1 focus:ring-brand-primary/20 focus:outline-none appearance-none transition-all duration-150 hover:bg-white/[0.08] hover:border-white/[0.15]'

const dateInputClass =
  'bg-white/[0.05] border border-white/[0.1] rounded-lg px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-primary/50 focus:ring-1 focus:ring-brand-primary/20 focus:outline-none transition-all duration-150 hover:bg-white/[0.08] hover:border-white/[0.15] [color-scheme:dark]'

export default function GlobalFilters() {
  const { filters, setFilter, resetFilters } = useFilterContext()
  const { data } = useFilters()
  const { data: dateInfo } = useDateRangeInfo(filters.dateRange)

  const handlePresetChange = (value: string) => {
    setFilter('dateRange', value)
    if (value !== 'custom') {
      setFilter('dateFrom', '')
      setFilter('dateTo', '')
    }
  }

  const handleDateFromChange = (value: string) => {
    setFilter('dateFrom', value)
    // Auto-fill dateTo from preset if not already set
    if (!filters.dateTo && dateInfo?.date_to) {
      setFilter('dateTo', dateInfo.date_to)
    }
    setFilter('dateRange', 'custom')
  }

  const handleDateToChange = (value: string) => {
    setFilter('dateTo', value)
    // Auto-fill dateFrom from preset if not already set
    if (!filters.dateFrom && dateInfo?.date_from) {
      setFilter('dateFrom', dateInfo.date_from)
    }
    setFilter('dateRange', 'custom')
  }

  const displayFrom = filters.dateFrom || dateInfo?.date_from || ''
  const displayTo = filters.dateTo || dateInfo?.date_to || ''

  const hasActiveFilters = filters.clientId || filters.technicianId || filters.priority || filters.techGroup || filters.status || filters.dateRange === 'custom'

  return (
    <div className="flex items-center gap-2.5 flex-wrap rounded-xl bg-white/[0.02] border border-white/[0.06] px-4 py-3">
      {/* Date filters */}
      <div className="relative inline-flex">
        <select value={filters.dateRange} onChange={e => handlePresetChange(e.target.value)} className={selectClass}>
          {DATE_RANGE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none" />
      </div>

      <input type="date" value={displayFrom} onChange={e => handleDateFromChange(e.target.value)}
        className={dateInputClass} />
      <span className="text-[10px] text-gray-600 font-medium uppercase">to</span>
      <input type="date" value={displayTo} onChange={e => handleDateToChange(e.target.value)}
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
