import { useFilterContext } from '../context/FilterContext'
import { useFilters } from '../api/hooks'
import { DATE_RANGE_OPTIONS } from '../utils/constants'

export default function GlobalFilters() {
  const { filters, setFilter, resetFilters } = useFilterContext()
  const { data } = useFilters()

  const selectClass =
    'bg-gray-800 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-gold/50 focus:outline-none appearance-none'

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <select
        value={filters.dateRange}
        onChange={e => setFilter('dateRange', e.target.value)}
        className={selectClass}
      >
        {DATE_RANGE_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <select
        value={filters.clientId}
        onChange={e => setFilter('clientId', e.target.value)}
        className={selectClass}
      >
        <option value="">All Clients</option>
        {data?.clients?.map((c: any) => (
          <option key={c.id} value={c.id}>{c.name}</option>
        ))}
      </select>

      <select
        value={filters.technicianId}
        onChange={e => setFilter('technicianId', e.target.value)}
        className={selectClass}
      >
        <option value="">All Technicians</option>
        {data?.technicians?.map((t: any) => (
          <option key={t.id} value={t.id}>{t.name}</option>
        ))}
      </select>

      <select
        value={filters.priority}
        onChange={e => setFilter('priority', e.target.value)}
        className={selectClass}
      >
        <option value="">All Priorities</option>
        {data?.priorities?.map((p: string) => (
          <option key={p} value={p}>{p}</option>
        ))}
      </select>

      {(filters.clientId || filters.technicianId || filters.priority || filters.status) && (
        <button
          onClick={resetFilters}
          className="text-xs text-gray-500 hover:text-gray-300 underline"
        >
          Clear filters
        </button>
      )}
    </div>
  )
}
