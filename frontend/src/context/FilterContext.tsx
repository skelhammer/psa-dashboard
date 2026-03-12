import { createContext, useContext, useState, ReactNode } from 'react'

interface FilterState {
  dateRange: string
  dateFrom: string
  dateTo: string
  clientId: string
  technicianId: string
  priority: string
  status: string
  category: string
  techGroup: string
}

interface FilterContextType {
  filters: FilterState
  setFilter: (key: keyof FilterState, value: string) => void
  resetFilters: () => void
  toParams: () => Record<string, string>
}

const defaults: FilterState = {
  dateRange: 'this_month',
  dateFrom: '',
  dateTo: '',
  clientId: '',
  technicianId: '',
  priority: '',
  status: '',
  category: '',
  techGroup: '',
}

const FilterContext = createContext<FilterContextType | null>(null)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<FilterState>(defaults)

  const setFilter = (key: keyof FilterState, value: string) => {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  const resetFilters = () => setFilters(defaults)

  const toParams = () => {
    const params: Record<string, string> = {}
    if (filters.dateRange === 'custom') {
      if (filters.dateFrom) params.date_from = filters.dateFrom
      if (filters.dateTo) params.date_to = filters.dateTo
      params.date_range = 'custom'
    } else if (filters.dateRange) {
      params.date_range = filters.dateRange
    }
    if (filters.clientId) params.client_id = filters.clientId
    if (filters.technicianId) params.technician_id = filters.technicianId
    if (filters.priority) params.priority = filters.priority
    if (filters.status) params.status = filters.status
    if (filters.category) params.category = filters.category
    if (filters.techGroup) params.tech_group = filters.techGroup
    return params
  }

  return (
    <FilterContext.Provider value={{ filters, setFilter, resetFilters, toParams }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilterContext() {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilterContext must be used within FilterProvider')
  return ctx
}
