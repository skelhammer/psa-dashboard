import { useState, FormEvent, useMemo } from 'react'
import {
  Lock,
  ShieldCheck,
  KeyRound,
  LogOut,
  Check,
  AlertCircle,
  Trash2,
  Loader2,
  History,
  Plug,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import {
  useMe,
  useSetupAdmin,
  useLogin,
  useLogout,
  useSecrets,
  useSetSecret,
  useDeleteSecret,
  useAudit,
  useChangePassword,
  useTestProvider,
  SecretView,
} from '../api/admin'

// Friendly provider headings, ordered for display
const PROVIDER_GROUPS: { provider: string; title: string; description: string }[] = [
  {
    provider: 'superops',
    title: 'SuperOps',
    description: 'API token used to sync tickets, clients, contracts, and technicians.',
  },
  {
    provider: 'zendesk',
    title: 'Zendesk',
    description: 'API token used for the secondary PSA provider.',
  },
  {
    provider: 'zoom',
    title: 'Zoom Phone',
    description: 'Server-to-Server OAuth credentials for the Zoom Phone integration.',
  },
]

function readErrorMessage(err: unknown): string {
  if (!err) return ''
  // axios error
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const anyErr = err as any
  return (
    anyErr?.response?.data?.detail ||
    anyErr?.message ||
    'Something went wrong'
  )
}

function formatTimestamp(ts: string | null): string {
  if (!ts) return 'never'
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

// ----- Setup form (first ever visit) -----

function SetupForm() {
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const setup = useSetupAdmin()
  const tooShort = pw.length > 0 && pw.length < 12
  const mismatch = confirm.length > 0 && pw !== confirm
  const canSubmit = pw.length >= 12 && pw === confirm && !setup.isPending

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setup.mutate(pw)
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <div className="rounded-2xl border border-white/[0.08] bg-[#0C0C0E] p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-lg bg-brand-primary/[0.12] border border-brand-primary/[0.25] flex items-center justify-center">
            <ShieldCheck size={18} className="text-brand-primary-light" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Set Admin Password</h2>
            <p className="text-xs text-gray-500">First time setup. Choose a strong password.</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label className="block text-[11px] font-medium text-gray-400 mb-1">
              New password
            </label>
            <input
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              autoFocus
              className="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
              placeholder="At least 12 characters"
            />
            {tooShort && (
              <p className="mt-1 text-[11px] text-amber-400">
                Password must be at least 12 characters.
              </p>
            )}
          </div>

          <div>
            <label className="block text-[11px] font-medium text-gray-400 mb-1">
              Confirm password
            </label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
              placeholder="Type it again"
            />
            {mismatch && (
              <p className="mt-1 text-[11px] text-amber-400">Passwords do not match.</p>
            )}
          </div>

          {setup.error && (
            <div className="flex items-start gap-2 p-2 rounded-lg bg-red-500/[0.08] border border-red-500/[0.2]">
              <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
              <p className="text-[11px] text-red-300">{readErrorMessage(setup.error)}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={!canSubmit}
            className={clsx(
              'w-full px-4 py-2 rounded-lg text-sm font-medium transition-all',
              canSubmit
                ? 'bg-brand-primary text-white hover:bg-brand-primary/90'
                : 'bg-white/[0.05] text-gray-600 cursor-not-allowed'
            )}
          >
            {setup.isPending ? 'Creating...' : 'Create admin and continue'}
          </button>

          <p className="text-[11px] text-gray-600 leading-relaxed pt-1">
            Save this password in your password manager. There is no email recovery.
            If you forget it, you can reset it from the server command line with
            <code className="px-1 py-0.5 bg-white/[0.05] rounded text-gray-400">
              python -m app.vault.cli set-admin-password
            </code>.
          </p>
        </form>
      </div>
    </div>
  )
}

// ----- Login form (returning visit, not authenticated) -----

function LoginForm() {
  const [pw, setPw] = useState('')
  const login = useLogin()

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!pw || login.isPending) return
    login.mutate(pw)
  }

  return (
    <div className="max-w-md mx-auto mt-12">
      <div className="rounded-2xl border border-white/[0.08] bg-[#0C0C0E] p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-9 h-9 rounded-lg bg-brand-primary/[0.12] border border-brand-primary/[0.25] flex items-center justify-center">
            <Lock size={18} className="text-brand-primary-light" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Sign In</h2>
            <p className="text-xs text-gray-500">Enter the admin password to manage settings.</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <label className="block text-[11px] font-medium text-gray-400 mb-1">
              Password
            </label>
            <input
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              autoFocus
              className="w-full px-3 py-2 rounded-lg bg-[#09090B] border border-white/[0.08] text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
            />
          </div>

          {login.error && (
            <div className="flex items-start gap-2 p-2 rounded-lg bg-red-500/[0.08] border border-red-500/[0.2]">
              <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
              <p className="text-[11px] text-red-300">{readErrorMessage(login.error)}</p>
            </div>
          )}

          <button
            type="submit"
            disabled={!pw || login.isPending}
            className={clsx(
              'w-full px-4 py-2 rounded-lg text-sm font-medium transition-all',
              pw && !login.isPending
                ? 'bg-brand-primary text-white hover:bg-brand-primary/90'
                : 'bg-white/[0.05] text-gray-600 cursor-not-allowed'
            )}
          >
            {login.isPending ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

// ----- One row in a provider card: edit/save/clear a single credential field -----

function SecretRow({ secret }: { secret: SecretView }) {
  // For text fields, the input is pre-filled with the current stored value
  // and Save is only enabled when the user has actually changed it. For
  // secret fields, the input starts empty and Save commits whatever the
  // user types as the new value.
  const initialDraft = !secret.secret && secret.value ? secret.value : ''
  const [draft, setDraft] = useState(initialDraft)
  const [savedFlash, setSavedFlash] = useState(false)
  const setSecret = useSetSecret()
  const deleteSecret = useDeleteSecret()

  const isDirty = secret.secret
    ? draft.length > 0
    : draft !== (secret.value ?? '')

  function onSave(e: FormEvent) {
    e.preventDefault()
    if (!isDirty || setSecret.isPending) return
    setSecret.mutate(
      { key: secret.key, value: draft },
      {
        onSuccess: () => {
          // Clear the input only for secret fields. For text fields keep
          // the new value visible so the user can see what they saved.
          if (secret.secret) setDraft('')
          setSavedFlash(true)
          setTimeout(() => setSavedFlash(false), 2000)
        },
      }
    )
  }

  function onClear() {
    if (!secret.is_set) return
    const noun = secret.secret ? 'secret' : 'value'
    if (!window.confirm(`Clear ${secret.label}? The provider will stop working until you set a new ${noun}.`)) return
    deleteSecret.mutate(secret.key)
  }

  const busy = setSecret.isPending || deleteSecret.isPending
  const inputType = secret.secret ? 'password' : 'text'
  const placeholder = secret.secret
    ? (secret.is_set ? 'Enter new value to replace' : 'Enter value')
    : (secret.is_set ? '' : 'Enter value')

  return (
    <div className="py-3 border-t border-white/[0.05] first:border-t-0">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div>
          <p className="text-[13px] font-medium text-gray-200">{secret.label}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={clsx(
                'inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium',
                secret.is_set
                  ? 'bg-emerald-500/[0.12] text-emerald-400 border border-emerald-500/[0.2]'
                  : 'bg-gray-500/[0.12] text-gray-400 border border-gray-500/[0.2]'
              )}
            >
              <span
                className={clsx(
                  'w-1 h-1 rounded-full',
                  secret.is_set ? 'bg-emerald-400' : 'bg-gray-500'
                )}
              />
              {secret.is_set ? 'Configured' : 'Not set'}
            </span>
            <span className="text-[10px] text-gray-600">
              Updated {formatTimestamp(secret.updated_at)}
            </span>
          </div>
        </div>
        {secret.is_set && (
          <button
            type="button"
            onClick={onClear}
            disabled={busy}
            className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] text-gray-500 hover:text-red-400 hover:bg-red-500/[0.08] border border-transparent hover:border-red-500/[0.2] transition-all"
            title="Clear this value"
          >
            <Trash2 size={12} />
            Clear
          </button>
        )}
      </div>

      <form onSubmit={onSave} className="flex gap-2">
        <input
          type={inputType}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          autoComplete={secret.secret ? 'new-password' : 'off'}
          className="flex-1 px-3 py-1.5 rounded-lg bg-[#09090B] border border-white/[0.08] text-[12px] text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
        />
        <button
          type="submit"
          disabled={!isDirty || busy}
          className={clsx(
            'px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all flex items-center gap-1',
            isDirty && !busy
              ? 'bg-brand-primary text-white hover:bg-brand-primary/90'
              : 'bg-white/[0.05] text-gray-600 cursor-not-allowed'
          )}
        >
          {setSecret.isPending && setSecret.variables?.key === secret.key ? (
            <Loader2 size={12} className="animate-spin" />
          ) : savedFlash ? (
            <Check size={12} />
          ) : null}
          {savedFlash ? 'Saved' : 'Save'}
        </button>
      </form>

      {(setSecret.error && setSecret.variables?.key === secret.key) ||
      (deleteSecret.error && deleteSecret.variables === secret.key) ? (
        <p className="mt-1 text-[11px] text-red-300">
          {readErrorMessage(setSecret.error || deleteSecret.error)}
        </p>
      ) : null}
    </div>
  )
}

// ----- Change password section -----

function ChangePasswordSection() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [savedFlash, setSavedFlash] = useState(false)
  const change = useChangePassword()

  const tooShort = next.length > 0 && next.length < 12
  const mismatch = confirm.length > 0 && next !== confirm
  const sameAsCurrent = current.length > 0 && next.length > 0 && current === next
  const canSubmit =
    current.length > 0 &&
    next.length >= 12 &&
    next === confirm &&
    !sameAsCurrent &&
    !change.isPending

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
          setConfirm('')
          setSavedFlash(true)
          setTimeout(() => setSavedFlash(false), 3000)
        },
      }
    )
  }

  return (
    <section className="rounded-2xl border border-white/[0.08] bg-[#0C0C0E] p-5">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-white">Change Admin Password</h2>
        <p className="text-[11px] text-gray-500">
          Rotate the password used to sign into this Settings page. Save the new
          one in your password manager before clicking save.
        </p>
      </div>

      <form onSubmit={onSubmit} className="space-y-2 max-w-md">
        <div>
          <label className="block text-[11px] font-medium text-gray-400 mb-1">
            Current password
          </label>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            autoComplete="current-password"
            className="w-full px-3 py-1.5 rounded-lg bg-[#09090B] border border-white/[0.08] text-[12px] text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
          />
        </div>

        <div>
          <label className="block text-[11px] font-medium text-gray-400 mb-1">
            New password
          </label>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            autoComplete="new-password"
            placeholder="At least 12 characters"
            className="w-full px-3 py-1.5 rounded-lg bg-[#09090B] border border-white/[0.08] text-[12px] text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
          />
          {tooShort && (
            <p className="mt-1 text-[11px] text-amber-400">
              Password must be at least 12 characters.
            </p>
          )}
          {sameAsCurrent && (
            <p className="mt-1 text-[11px] text-amber-400">
              New password must be different from the current one.
            </p>
          )}
        </div>

        <div>
          <label className="block text-[11px] font-medium text-gray-400 mb-1">
            Confirm new password
          </label>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            className="w-full px-3 py-1.5 rounded-lg bg-[#09090B] border border-white/[0.08] text-[12px] text-white placeholder-gray-600 focus:outline-none focus:border-brand-primary/50"
          />
          {mismatch && (
            <p className="mt-1 text-[11px] text-amber-400">Passwords do not match.</p>
          )}
        </div>

        {change.error && (
          <div className="flex items-start gap-2 p-2 rounded-lg bg-red-500/[0.08] border border-red-500/[0.2]">
            <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
            <p className="text-[11px] text-red-300">{readErrorMessage(change.error)}</p>
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <button
            type="submit"
            disabled={!canSubmit}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all flex items-center gap-1',
              canSubmit
                ? 'bg-brand-primary text-white hover:bg-brand-primary/90'
                : 'bg-white/[0.05] text-gray-600 cursor-not-allowed'
            )}
          >
            {change.isPending ? (
              <Loader2 size={12} className="animate-spin" />
            ) : savedFlash ? (
              <Check size={12} />
            ) : null}
            {savedFlash ? 'Password updated' : 'Update password'}
          </button>
        </div>
      </form>
    </section>
  )
}

// ----- Test connection button (per provider card header) -----

function TestConnectionButton({ provider }: { provider: string }) {
  const test = useTestProvider()
  const result = test.data

  function onClick() {
    test.mutate(provider)
  }

  return (
    <div className="flex items-center gap-2">
      {result && (
        <span
          className={clsx(
            'inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded font-medium',
            result.ok
              ? 'bg-emerald-500/[0.12] text-emerald-400 border border-emerald-500/[0.2]'
              : 'bg-red-500/[0.12] text-red-300 border border-red-500/[0.2]'
          )}
          title={result.message}
        >
          {result.ok ? <Check size={10} /> : <X size={10} />}
          <span className="max-w-[260px] truncate">{result.message}</span>
        </span>
      )}
      <button
        type="button"
        onClick={onClick}
        disabled={test.isPending}
        className={clsx(
          'inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium border transition-all',
          test.isPending
            ? 'text-gray-600 border-white/[0.05] cursor-not-allowed'
            : 'text-gray-400 border-white/[0.08] hover:text-brand-primary hover:border-brand-primary/30 hover:bg-brand-primary/[0.06]'
        )}
        title="Verify the stored credentials by hitting the upstream API"
      >
        {test.isPending ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <Plug size={12} />
        )}
        Test connection
      </button>
    </div>
  )
}

// ----- Audit log table -----

function AuditLog() {
  const audit = useAudit(true)

  if (audit.isLoading) {
    return (
      <p className="text-[11px] text-gray-600">Loading audit log...</p>
    )
  }
  if (audit.error || !audit.data) {
    return (
      <p className="text-[11px] text-red-300">
        Failed to load audit log: {readErrorMessage(audit.error)}
      </p>
    )
  }
  if (audit.data.length === 0) {
    return <p className="text-[11px] text-gray-600">No audit events yet.</p>
  }
  return (
    <div className="overflow-hidden rounded-lg border border-white/[0.05]">
      <table className="w-full text-[11px]">
        <thead className="bg-white/[0.02]">
          <tr className="text-left text-gray-500">
            <th className="px-3 py-2 font-medium">When</th>
            <th className="px-3 py-2 font-medium">Actor</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Key</th>
            <th className="px-3 py-2 font-medium">IP</th>
          </tr>
        </thead>
        <tbody>
          {audit.data.map((e, i) => (
            <tr key={i} className="border-t border-white/[0.05]">
              <td className="px-3 py-1.5 text-gray-400 whitespace-nowrap">
                {formatTimestamp(e.ts)}
              </td>
              <td className="px-3 py-1.5 text-gray-300">{e.actor}</td>
              <td className="px-3 py-1.5 text-gray-300">{e.action}</td>
              <td className="px-3 py-1.5 text-gray-400 font-mono">{e.key}</td>
              <td className="px-3 py-1.5 text-gray-500">{e.ip || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ----- Authenticated view -----

function AuthenticatedSettings({ username }: { username: string }) {
  const secrets = useSecrets(true)
  const logout = useLogout()

  const grouped = useMemo(() => {
    if (!secrets.data) return new Map<string, SecretView[]>()
    const m = new Map<string, SecretView[]>()
    for (const s of secrets.data) {
      const list = m.get(s.provider) || []
      list.push(s)
      m.set(s.provider, list)
    }
    return m
  }, [secrets.data])

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-brand-primary/[0.12] border border-brand-primary/[0.25] flex items-center justify-center">
            <KeyRound size={18} className="text-brand-primary-light" />
          </div>
          <div>
            <h1 className="text-base font-semibold text-white">Settings</h1>
            <p className="text-[11px] text-gray-500">
              Signed in as <span className="text-gray-400">{username}</span>
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => logout.mutate()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium text-gray-400 hover:text-gray-200 hover:bg-white/[0.06] border border-transparent hover:border-white/[0.1] transition-all"
        >
          <LogOut size={12} />
          Sign out
        </button>
      </div>

      {secrets.isLoading && (
        <p className="text-[12px] text-gray-500">Loading secrets...</p>
      )}
      {secrets.error && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-red-500/[0.08] border border-red-500/[0.2]">
          <AlertCircle size={14} className="text-red-400 mt-0.5 shrink-0" />
          <p className="text-[12px] text-red-300">{readErrorMessage(secrets.error)}</p>
        </div>
      )}

      {secrets.data && (
        <>
          {PROVIDER_GROUPS.map((group) => {
            const items = grouped.get(group.provider) || []
            if (items.length === 0) return null
            const allSet = items.every((s) => s.is_set)
            return (
              <section
                key={group.provider}
                className="rounded-2xl border border-white/[0.08] bg-[#0C0C0E] p-5"
              >
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-sm font-semibold text-white">{group.title}</h2>
                    <p className="text-[11px] text-gray-500">{group.description}</p>
                  </div>
                  {allSet && <TestConnectionButton provider={group.provider} />}
                </div>
                {items.map((secret) => (
                  <SecretRow key={secret.key} secret={secret} />
                ))}
              </section>
            )
          })}

          <ChangePasswordSection />

          <section className="rounded-2xl border border-white/[0.08] bg-[#0C0C0E] p-5">
            <div className="flex items-center gap-2 mb-3">
              <History size={14} className="text-gray-500" />
              <h2 className="text-sm font-semibold text-white">Audit Log</h2>
            </div>
            <AuditLog />
          </section>
        </>
      )}
    </div>
  )
}

// ----- Top level page: switches between three states -----

export default function Settings() {
  const me = useMe()

  if (me.isLoading) {
    return (
      <p className="text-[12px] text-gray-500 max-w-md mx-auto mt-12">
        Loading...
      </p>
    )
  }
  if (me.error || !me.data) {
    return (
      <div className="max-w-md mx-auto mt-12 p-3 rounded-lg bg-red-500/[0.08] border border-red-500/[0.2]">
        <p className="text-[12px] text-red-300">
          Cannot reach the dashboard backend. Make sure it is running, then refresh.
        </p>
      </div>
    )
  }
  if (me.data.setup_required) return <SetupForm />
  if (!me.data.authenticated) return <LoginForm />
  return <AuthenticatedSettings username={me.data.username || 'admin'} />
}
