import { useFilterContext } from '../context/FilterContext'
import { useFilters, useDateRangeInfo } from '../api/hooks'
import { DATE_RANGE_OPTIONS } from '../utils/constants'

const selectClass =
  'bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-gray-300 focus:border-brand-primary/50 focus:ring-1 focus:ring-brand-primary/20 focus:outline-none appearance-none transition-all duration-150 hover:bg-white/[0.06] hover:border-white/[0.12]'

const dateInputClass =
  'bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-1.5 text-xs text-gray-300 focus:border-brand-primary/50 focus:ring-1 focus:ring-brand-primary/20 focus:outline-none transition-all duration-150 hover:bg-white/[0.06] hover:border-white/[0.12] [color-scheme:dark]'

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
    setFilter('dateRange', 'custom')
  }

  const handleDateToChange = (value: string) => {
    setFilter('dateTo', value)
    setFilter('dateRange', 'custom')
  }

  const displayFrom = filters.dateFrom || dateInfo?.date_from || ''
  const displayTo = filters.dateTo || dateInfo?.date_to || ''

  const hasActiveFilters = filters.clientId || filters.technicianId || filters.priority || filters.techGroup || filters.status || filters.dateRange === 'custom'

  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <select value={filters.dateRange} onChange={e => handlePresetChange(e.target.value)} className={selectClass}>
        {DATE_RANGE_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <input type="date" value={displayFrom} onChange={e => handleDateFromChange(e.target.value)}
        className={dateInputClass} />
      <span className="text-xs text-gray-500">to</span>
      <input type="date" value={displayTo} onChange={e => handleDateToChange(e.target.value)}
        className={dateInputClass} />

      <select value={filters.clientId} onChange={e => setFilter('clientId', e.target.value)} className={selectClass}>
        <option value="">All Clients</option>
        {data?.clients?.map((c: any) => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>

      <select value={filters.technicianId} onChange={e => setFilter('technicianId', e.target.value)} className={selectClass}>
        <option value="">All Technicians</option>
        {data?.technicians?.map((t: any) => (
          <option key={t.id} value={t.id}>{t.name}</option>
        ))}
      </select>

      <select value={filters.priority} onChange={e => setFilter('priority', e.target.value)} className={selectClass}>
        <option value="">All Priorities</option>
        {data?.priorities?.map((p: string) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>

      <select value={filters.techGroup} onChange={e => setFilter('techGroup', e.target.value)} className={selectClass}>
        <option value="">All Groups</option>
        {data?.groups?.map((g: string) => (
          <option key={g} value={g}>{g}</option>
        ))}
      </select>

      {hasActiveFilters && (
        <button
          onClick={resetFilters}
          className="text-xs text-gray-500 hover:text-brand-primary transition-colors duration-150"
        >
          Clear filters
        </button>
      )}
    </div>
  )
}
