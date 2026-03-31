import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query'
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
    placeholderData: keepPreviousData,
  })
}

export function useOverviewCharts(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['overview-charts', params],
    queryFn: () => api.get('/overview/charts', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

// Manage to Zero
export function useManageToZero(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['manage-to-zero', params],
    queryFn: () => api.get('/manage-to-zero', { params }).then(r => r.data),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  })
}

export function useMtzDrilldown(cardType: string | null, params?: Record<string, string>) {
  return useQuery({
    queryKey: ['mtz-drilldown', cardType, params],
    queryFn: () => api.get(`/manage-to-zero/${cardType}`, { params }).then(r => r.data),
    enabled: !!cardType,
    placeholderData: keepPreviousData,
  })
}

// Work Queue
export function useWorkQueue(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['work-queue', params],
    queryFn: () => api.get('/work-queue', { params }).then(r => r.data),
    refetchInterval: 30_000,
    placeholderData: keepPreviousData,
  })
}

// Technicians
export function useTechnicians(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['technicians', params],
    queryFn: () => api.get('/technicians', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

export function useTechnicianDetail(techId: string | undefined, params?: Record<string, string>) {
  return useQuery({
    queryKey: ['technician', techId, params],
    queryFn: () => api.get(`/technicians/${techId}`, { params }).then(r => r.data),
    enabled: !!techId,
    placeholderData: keepPreviousData,
  })
}

// Clients
export function useClients(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['clients', params],
    queryFn: () => api.get('/clients', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

export function useClientDetail(clientId: string | undefined, params?: Record<string, string>) {
  return useQuery({
    queryKey: ['client', clientId, params],
    queryFn: () => api.get(`/clients/${clientId}`, { params }).then(r => r.data),
    enabled: !!clientId,
    placeholderData: keepPreviousData,
  })
}

// Billing
export function useBillingFlags(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['billing-flags', params],
    queryFn: () => api.get('/billing/flags', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

export function useBillingSummary(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['billing-summary', params],
    queryFn: () => api.get('/billing/summary', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

// Executive Report
export function useExecutiveReport(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['executive-report', params],
    queryFn: () => api.get('/executive/report', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

export function useExecutiveCharts(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['executive-charts', params],
    queryFn: () => api.get('/executive/charts', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

// Phone Analytics
export function usePhoneOverview(days: number = 30) {
  return useQuery({
    queryKey: ['phone-overview', days],
    queryFn: () => api.get('/phone/overview', { params: { days } }).then(r => r.data),
  })
}

export function usePhoneCharts(days: number = 30) {
  return useQuery({
    queryKey: ['phone-charts', days],
    queryFn: () => api.get('/phone/charts', { params: { days } }).then(r => r.data),
  })
}

export function usePhoneAgents(days: number = 30) {
  return useQuery({
    queryKey: ['phone-agents', days],
    queryFn: () => api.get('/phone/agents', { params: { days } }).then(r => r.data),
  })
}

export function usePhoneQueues(days: number = 30) {
  return useQuery({
    queryKey: ['phone-queues', days],
    queryFn: () => api.get('/phone/queues', { params: { days } }).then(r => r.data),
  })
}

// Alerts
export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: () => api.get('/alerts/active').then(r => r.data),
    refetchInterval: 60_000,
  })
}

// Executive Summary (CEO)
export function useExecutiveSummary() {
  return useQuery({
    queryKey: ['executive-summary'],
    queryFn: () => api.get('/executive/summary').then(r => r.data),
  })
}

// Client Profitability
export function useClientProfitability(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['client-profitability', params],
    queryFn: () => api.get('/clients/profitability', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

// Teams
export function useTeams(params?: Record<string, string>) {
  return useQuery({
    queryKey: ['teams', params],
    queryFn: () => api.get('/teams', { params }).then(r => r.data),
    placeholderData: keepPreviousData,
  })
}

// Update technician dashboard role
export function useUpdateTechRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ techId, dashboard_roles }: { techId: string; dashboard_roles: string[] }) =>
      api.patch(`/technicians/${techId}/role`, { dashboard_roles }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['technicians'] })
      qc.invalidateQueries({ queryKey: ['teams'] })
      qc.invalidateQueries({ queryKey: ['alerts'] })
      qc.invalidateQueries({ queryKey: ['executive-summary'] })
    },
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
