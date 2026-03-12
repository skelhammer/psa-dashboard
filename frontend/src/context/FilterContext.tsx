import { createContext, useContext, useState, ReactNode } from 'react'

interface FilterState {
  dateRange: string
  clientId: string
  technicianId: string
  priority: string
  status: string
  category: string
}

interface FilterContextType {
  filters: FilterState
  setFilter: (key: keyof FilterState, value: string) => void
  resetFilters: () => void
  toParams: () => Record<string, string>
}

const defaults: FilterState = {
  dateRange: 'this_month',
  clientId: '',
  technicianId: '',
  priority: '',
  status: '',
  category: '',
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
    if (filters.dateRange) params.date_range = filters.dateRange
    if (filters.clientId) params.client_id = filters.clientId
    if (filters.technicianId) params.technician_id = filters.technicianId
    if (filters.priority) params.priority = filters.priority
    if (filters.status) params.status = filters.status
    if (filters.category) params.category = filters.category
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
