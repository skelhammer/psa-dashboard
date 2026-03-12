import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'

// Sync
export function useSyncStatus() {
  return useQuery({
    queryKey: ['sync-status'],
    queryFn: () => api.get('/sync/status').then(r => r.data),
    refetchInterval: 10_000,
  })
}

export function useTriggerSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/sync/trigger').then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries()
    },
  })
}

export function useTriggerFullSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/sync/full').then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries()
    },
  })
}

// Filters
export function useFilters() {
  return useQuery({
    queryKey: ['filters'],
    queryFn: () => api.get('/filters').then(r => r.data),
    staleTime: 120_000,
  })
}

export function useDateRangeInfo(dateRange: string) {
  return useQuery({
    queryKey: ['date-range-info', dateRange],
    queryFn: () => api.get('/filters/date-range', { params: { date_range: dateRange } }).then(r => r.data),
    staleTime: 60_000,
    enabled: dateRange !== 'custom',
  })
}

// Overview
export function useOverview(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['overview', params],
    queryFn: () => api.get('/overview', { params }).then(r => r.data),
  })
}

export function useOverviewCharts(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['overview-charts', params],
    queryFn: () => api.get('/overview/charts', { params }).then(r => r.data),
  })
}

// Manage to Zero
export function useManageToZero() {
  return useQuery({
    queryKey: ['manage-to-zero'],
    queryFn: () => api.get('/manage-to-zero').then(r => r.data),
    refetchInterval: 30_000,
  })
}

export function useMtzDrilldown(cardType: string | null) {
  return useQuery({
    queryKey: ['mtz-drilldown', cardType],
    queryFn: () => api.get(`/manage-to-zero/${cardType}`).then(r => r.data),
    enabled: !!cardType,
  })
}

// Work Queue
export function useWorkQueue(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['work-queue', params],
    queryFn: () => api.get('/work-queue', { params }).then(r => r.data),
    refetchInterval: 30_000,
  })
}

// Technicians
export function useTechnicians(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['technicians', params],
    queryFn: () => api.get('/technicians', { params }).then(r => r.data),
  })
}

export function useTechnicianDetail(techId: string | undefined) {
  return useQuery({
    queryKey: ['technician', techId],
    queryFn: () => api.get(`/technicians/${techId}`).then(r => r.data),
    enabled: !!techId,
  })
}

// Billing
export function useBillingFlags(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['billing-flags', params],
    queryFn: () => api.get('/billing/flags', { params }).then(r => r.data),
  })
}

export function useBillingSummary(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['billing-summary', params],
    queryFn: () => api.get('/billing/summary', { params }).then(r => r.data),
  })
}

export function useResolveFlag() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ flagId, ...body }: { flagId: number; resolved_by: string; resolution_note: string }) =>
      api.patch(`/billing/flags/${flagId}/resolve`, body).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['billing-flags'] })
      qc.invalidateQueries({ queryKey: ['billing-summary'] })
      qc.invalidateQueries({ queryKey: ['manage-to-zero'] })
    },
  })
}
