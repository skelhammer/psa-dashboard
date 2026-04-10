import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import api from './client'

// ----- Types matching the backend response shapes -----

export type MeResponse = {
  authenticated: boolean
  setup_required: boolean
  username: string | null
}

export type SecretView = {
  key: string
  label: string
  provider: string
  is_set: boolean
  // True if this is a true secret (API token). False for non-secret
  // credential fields like usernames or subdomains, where the current
  // stored value is also returned in `value` so the UI can show it.
  secret: boolean
  value: string | null
  updated_at: string | null
}

export type SecretMutationResponse = {
  ok: boolean
  key: string
  reload: {
    reloaded: boolean
    kind?: string
    provider?: string | null
    reason?: string
  }
}

export type AuditEntry = {
  ts: string
  actor: string
  action: string
  key: string
  ip: string | null
  user_agent: string | null
}

export type TestResult = {
  ok: boolean
  provider: string
  message: string
}

// ----- Auth hooks -----

export function useMe() {
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: () => api.get<MeResponse>('/auth/me').then(r => r.data),
    // Refetch every minute so a session timeout is detected reasonably soon.
    refetchInterval: 60_000,
    retry: false,
  })
}

export function useSetupAdmin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (password: string) =>
      api.post('/auth/setup', { password }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auth', 'me'] })
      qc.invalidateQueries({ queryKey: ['admin'] })
    },
  })
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (password: string) =>
      api.post('/auth/login', { password }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auth', 'me'] })
      qc.invalidateQueries({ queryKey: ['admin'] })
    },
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout').then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['auth', 'me'] })
      qc.removeQueries({ queryKey: ['admin'] })
    },
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (vars: { current_password: string; new_password: string }) =>
      api.post('/auth/password', vars).then(r => r.data),
  })
}

// ----- Admin secrets hooks -----

export function useSecrets(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'secrets'],
    queryFn: () => api.get<SecretView[]>('/admin/secrets').then(r => r.data),
    enabled,
    retry: false,
  })
}

export function useSetSecret() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: string }) =>
      api
        .put<SecretMutationResponse>(
          `/admin/secrets/${encodeURIComponent(key)}`,
          { value }
        )
        .then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'secrets'] })
      qc.invalidateQueries({ queryKey: ['admin', 'audit'] })
      // Hot reload may have changed which provider is active; refresh sync status.
      qc.invalidateQueries({ queryKey: ['sync-status'] })
    },
  })
}

export function useDeleteSecret() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) =>
      api
        .delete<SecretMutationResponse>(
          `/admin/secrets/${encodeURIComponent(key)}`
        )
        .then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin', 'secrets'] })
      qc.invalidateQueries({ queryKey: ['admin', 'audit'] })
      qc.invalidateQueries({ queryKey: ['sync-status'] })
    },
  })
}

export function useAudit(enabled: boolean) {
  return useQuery({
    queryKey: ['admin', 'audit'],
    queryFn: () => api.get<AuditEntry[]>('/admin/audit').then(r => r.data),
    enabled,
    retry: false,
  })
}

export function useTestProvider() {
  return useMutation({
    mutationFn: (provider: string) =>
      api
        .post<TestResult>(`/admin/secrets/test/${encodeURIComponent(provider)}`)
        .then(r => r.data),
  })
}
