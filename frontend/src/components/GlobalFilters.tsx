import { useFilterContext } from '../context/FilterContext'
import { useFilters, useDateRangeInfo } from '../api/hooks'
import { DATE_RANGE_OPTIONS } from '../utils/constants'

export default function GlobalFilters() {
  const { filters, setFilter, resetFilters } = useFilterContext()
  const { data } = useFilters()
  const { data: dateInfo } = useDateRangeInfo(filters.dateRange)

  const selectClass =
    'bg-gray-800 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-gold/50 focus:outline-none appearance-none'

  const dateInputClass =
    'bg-gray-800 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-300 focus:border-brand-gold/50 focus:outline-none [color-scheme:dark]'

  // When a preset is selected, populate the date inputs from the resolved range
  const handlePresetChange = (value: string) => {
    setFilter('dateRange', value)
    // Clear custom dates so the preset takes effect
    if (value !== 'custom') {
      setFilter('dateFrom', '')
      setFilter('dateTo', '')
    }
  }

  // When a date input changes, switch to custom mode
  const handleDateFromChange = (value: string) => {
    setFilter('dateFrom', value)
    setFilter('dateRange', 'custom')
  }

  const handleDateToChange = (value: string) => {
    setFilter('dateTo', value)
    setFilter('dateRange', 'custom')
  }

  // Show resolved dates from preset, or custom dates if set
  const displayFrom = filters.dateFrom || dateInfo?.date_from || ''
  const displayTo = filters.dateTo || dateInfo?.date_to || ''

  return (
    <div className="flex items-center gap-3 flex-wrap">
      <select
        value={filters.dateRange}
        onChange={e => handlePresetChange(e.target.value)}
        className={selectClass}
      >
        {DATE_RANGE_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>

      <input
        type="date"
        value={displayFrom}
        onChange={e => handleDateFromChange(e.target.value)}
        className={dateInputClass}
      />
      <span className="text-xs text-gray-500">to</span>
      <input
        type="date"
        value={displayTo}
        onChange={e => handleDateToChange(e.target.value)}
        className={dateInputClass}
      />

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

      {(filters.clientId || filters.technicianId || filters.priority || filters.status || filters.dateRange === 'custom') && (
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
