import { useState, useMemo } from 'react'
import {
  useContracts,
  useContractClientPicker,
  useCreateContract,
  useUpdateContract,
  useDeleteContract,
} from '../api/hooks'
import { FileText, Plus, Pencil, Trash2, X, AlertTriangle, Search } from 'lucide-react'
import clsx from 'clsx'

type Contract = {
  contract_id: string
  client_id: string
  client_name: string
  contract_type: string
  contract_name: string | null
  status: string
  start_date: string | null
  end_date: string | null
  term_length_years: number | null
  source: string
  notes: string | null
  days_until_expiry: number | null
  expiry_bucket: string
}

type FilterKey = 'active' | 'expiring_30' | 'expiring_60' | 'expiring_90' | 'expired' | 'no_end_date' | 'all'
type PlanKey = 'msp_all' | 'msp_basic' | 'msp_advanced' | 'msp_premium' | 'msp_platinum' | 'all'

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'expiring_30', label: 'Expiring < 30d' },
  { key: 'expiring_60', label: 'Expiring < 60d' },
  { key: 'expiring_90', label: 'Expiring < 90d' },
  { key: 'expired', label: 'Expired' },
  { key: 'no_end_date', label: 'No End Date' },
  { key: 'active', label: 'Active' },
]

const PLANS: { key: PlanKey; label: string }[] = [
  { key: 'msp_all', label: 'All MSP' },
  { key: 'msp_basic', label: 'Basic' },
  { key: 'msp_advanced', label: 'Advanced' },
  { key: 'msp_premium', label: 'Premium' },
  { key: 'msp_platinum', label: 'Platinum' },
  { key: 'all', label: 'All Contracts' },
]

const CONTRACT_TYPES = [
  { value: 'managed', label: 'Managed Service' },
  { value: 'hourly', label: 'Hourly / T&M' },
  { value: 'flat_rate', label: 'Flat Rate' },
  { value: 'other', label: 'Other' },
]

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function daysCell(days: number | null, bucket: string) {
  if (days === null) {
    return <span className="text-gray-500 text-xs">No end date</span>
  }
  const label = days < 0 ? `${Math.abs(days)}d ago` : `${days}d`
  const color =
    bucket === 'expired'
      ? 'text-red-400'
      : bucket === 'expiring_30'
        ? 'text-red-400'
        : bucket === 'expiring_60'
          ? 'text-orange-400'
          : bucket === 'expiring_90'
            ? 'text-yellow-400'
            : 'text-emerald-400'
  return <span className={clsx('tabular-nums font-semibold', color)}>{label}</span>
}

function sourceBadge(source: string) {
  if (source === 'manual') {
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-purple-500/15 text-purple-300 border-purple-500/30">
        MANUAL
      </span>
    )
  }
  return (
    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold border bg-blue-500/15 text-blue-300 border-blue-500/30">
      SYNCED
    </span>
  )
}

export default function Contracts() {
  const [filter, setFilter] = useState<FilterKey>('all')
  const [plan, setPlan] = useState<PlanKey>('msp_all')
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<Contract | null>(null)
  const [showAdd, setShowAdd] = useState(false)

  const { data, isLoading } = useContracts(filter, plan, search || undefined)

  const contracts: Contract[] = data?.contracts || []
  const summary = data?.summary || {}

  return (
    <div className="space-y-6 animate-slide-up">
      <div className="page-header flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <FileText size={20} className="text-brand-primary" />
            Contracts
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            SuperOps client contracts sorted by expiration. Manual entries and edits will not be overwritten by sync.
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-brand-primary/20 text-brand-primary-light border border-brand-primary/30 hover:bg-brand-primary/30 transition-colors"
        >
          <Plus size={14} />
          Add Contract
        </button>
      </div>

      {/* Plan filter chips */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-600 mr-1">Plan</span>
        {PLANS.map(p => (
          <button
            key={p.key}
            onClick={() => setPlan(p.key)}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
              plan === p.key
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                : 'bg-white/[0.03] text-gray-400 border-white/[0.08] hover:bg-white/[0.06] hover:text-gray-200'
            )}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Status filter chips + search */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-600 mr-1">Status</span>
        {FILTERS.map(f => {
          const count = summary[f.key]
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={clsx(
                'px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
                filter === f.key
                  ? 'bg-brand-primary/20 text-brand-primary-light border-brand-primary/30'
                  : 'bg-white/[0.03] text-gray-400 border-white/[0.08] hover:bg-white/[0.06] hover:text-gray-200'
              )}
            >
              {f.label}
              {count != null && (
                <span className="ml-1.5 text-gray-500 tabular-nums">({count})</span>
              )}
            </button>
          )
        })}

        <div className="flex-1" />

        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by client..."
            className="pl-8 pr-3 py-1.5 rounded-lg text-xs bg-white/[0.03] border border-white/[0.08] text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-brand-primary/40 w-56"
          />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-white/[0.08] shadow-lg shadow-black/20">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[#111113] border-b border-white/[0.08]">
              {[
                'Client', 'Contract', 'Type', 'Start', 'End', 'Term', 'Expires In', 'Source', 'Notes', '',
              ].map(h => (
                <th key={h} className="px-3 py-2.5 text-left text-xs font-medium text-gray-500 whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/50">
            {isLoading && (
              <tr>
                <td colSpan={10} className="px-3 py-10 text-center text-gray-500">Loading...</td>
              </tr>
            )}
            {!isLoading && contracts.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-10 text-center text-gray-500">
                  No contracts match this filter.
                </td>
              </tr>
            )}
            {contracts.map(c => (
              <tr
                key={c.contract_id}
                onClick={() => setEditing(c)}
                className="hover:bg-zinc-800/30 transition-colors cursor-pointer"
              >
                <td className="px-3 py-2.5 font-medium text-brand-primary-light">{c.client_name}</td>
                <td className="px-3 py-2.5 text-gray-300">{c.contract_name || '—'}</td>
                <td className="px-3 py-2.5 text-xs text-gray-400 capitalize">{c.contract_type?.replace('_', ' ')}</td>
                <td className="px-3 py-2.5 tabular-nums text-xs text-gray-400">{formatDate(c.start_date)}</td>
                <td className="px-3 py-2.5 tabular-nums text-xs text-gray-300">{formatDate(c.end_date)}</td>
                <td className="px-3 py-2.5 tabular-nums text-xs">
                  {c.term_length_years ? `${c.term_length_years}yr` : <span className="text-gray-600">—</span>}
                </td>
                <td className="px-3 py-2.5">{daysCell(c.days_until_expiry, c.expiry_bucket)}</td>
                <td className="px-3 py-2.5">{sourceBadge(c.source)}</td>
                <td className="px-3 py-2.5 text-xs text-gray-400 max-w-[220px] truncate" title={c.notes || ''}>
                  {c.notes || <span className="text-gray-600">—</span>}
                </td>
                <td className="px-3 py-2.5">
                  <Pencil size={14} className="text-gray-600" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showAdd && (
        <ContractDialog
          mode="create"
          onClose={() => setShowAdd(false)}
        />
      )}
      {editing && (
        <ContractDialog
          mode="edit"
          contract={editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  )
}

type DialogProps =
  | { mode: 'create'; onClose: () => void; contract?: undefined }
  | { mode: 'edit'; contract: Contract; onClose: () => void }

function ContractDialog(props: DialogProps) {
  const { mode, onClose } = props
  const existing = mode === 'edit' ? props.contract : undefined

  const { data: pickerData } = useContractClientPicker()
  const clientOptions: { id: string; name: string }[] = pickerData?.clients || []

  const [clientId, setClientId] = useState(existing?.client_id || '')
  const [contractName, setContractName] = useState(existing?.contract_name || '')
  const [contractType, setContractType] = useState(existing?.contract_type || 'managed')
  const [startDate, setStartDate] = useState(existing?.start_date?.slice(0, 10) || '')
  const [endDate, setEndDate] = useState(existing?.end_date?.slice(0, 10) || '')
  const [termYears, setTermYears] = useState<number | ''>(existing?.term_length_years ?? '')
  const [notes, setNotes] = useState(existing?.notes || '')
  const [status, setStatus] = useState(existing?.status || 'active')
  const [confirmDelete, setConfirmDelete] = useState(false)

  const createMut = useCreateContract()
  const updateMut = useUpdateContract()
  const deleteMut = useDeleteContract()
  const busy = createMut.isPending || updateMut.isPending || deleteMut.isPending

  // Auto-compute end date when start + term is set (only for create or if end empty)
  const derivedEnd = useMemo(() => {
    if (!startDate || !termYears) return ''
    const d = new Date(startDate)
    if (isNaN(d.getTime())) return ''
    d.setFullYear(d.getFullYear() + Number(termYears))
    return d.toISOString().slice(0, 10)
  }, [startDate, termYears])

  const handleUseDerivedEnd = () => {
    if (derivedEnd) setEndDate(derivedEnd)
  }

  const canSave =
    (mode === 'create' ? !!clientId : true) &&
    !busy

  const handleSave = async () => {
    const body = {
      client_id: clientId || undefined,
      contract_name: contractName || null,
      contract_type: contractType,
      start_date: startDate || null,
      end_date: endDate || null,
      term_length_years: termYears === '' ? null : Number(termYears),
      notes: notes || null,
      status,
    }
    if (mode === 'create') {
      await createMut.mutateAsync(body)
    } else {
      await updateMut.mutateAsync({ contractId: existing!.contract_id, ...body })
    }
    onClose()
  }

  const handleDelete = async () => {
    if (!existing) return
    await deleteMut.mutateAsync(existing.contract_id)
    onClose()
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div className="bg-[#0C0C0E] border border-white/[0.12] rounded-2xl shadow-2xl w-full max-w-lg pointer-events-auto max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.08]">
            <h3 className="text-base font-bold text-white">
              {mode === 'create' ? 'Add Contract' : 'Edit Contract'}
            </h3>
            <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
              <X size={18} />
            </button>
          </div>

          <div className="p-5 space-y-4">
            {mode === 'edit' && existing?.source === 'synced' && (
              <div className="flex items-start gap-2 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-xs text-yellow-300">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <div>
                  This contract came from SuperOps. Saving any change will flip it to manual so future syncs will not overwrite your edits.
                </div>
              </div>
            )}

            {/* Client picker (create only) */}
            {mode === 'create' ? (
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Client</label>
                <select
                  value={clientId}
                  onChange={e => setClientId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 focus:outline-none focus:border-brand-primary/40"
                >
                  <option value="">Select a client...</option>
                  {clientOptions.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            ) : (
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Client</label>
                <div className="px-3 py-2 rounded-lg text-sm bg-white/[0.02] border border-white/[0.05] text-gray-400">
                  {existing?.client_name}
                </div>
              </div>
            )}

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Contract Name</label>
              <input
                type="text"
                value={contractName}
                onChange={e => setContractName(e.target.value)}
                placeholder="e.g. MSP Gold"
                className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-brand-primary/40"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Contract Type</label>
              <select
                value={contractType}
                onChange={e => setContractType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 focus:outline-none focus:border-brand-primary/40"
              >
                {CONTRACT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">Start Date</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={e => setStartDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 focus:outline-none focus:border-brand-primary/40"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1.5">End Date</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={e => setEndDate(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 focus:outline-none focus:border-brand-primary/40"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Term Length</label>
              <div className="flex gap-2">
                {[1, 2, 3].map(y => (
                  <button
                    key={y}
                    type="button"
                    onClick={() => setTermYears(y)}
                    className={clsx(
                      'px-4 py-2 rounded-lg text-sm font-medium transition-colors border',
                      termYears === y
                        ? 'bg-brand-primary/20 text-brand-primary-light border-brand-primary/30'
                        : 'bg-white/[0.03] text-gray-400 border-white/[0.08] hover:bg-white/[0.06]'
                    )}
                  >
                    {y} year{y > 1 ? 's' : ''}
                  </button>
                ))}
                {termYears !== '' && (
                  <button
                    type="button"
                    onClick={() => setTermYears('')}
                    className="px-2 py-2 text-xs text-gray-500 hover:text-gray-300"
                  >
                    clear
                  </button>
                )}
              </div>
              {derivedEnd && derivedEnd !== endDate && (
                <button
                  type="button"
                  onClick={handleUseDerivedEnd}
                  className="mt-2 text-[11px] text-brand-primary-light hover:underline"
                >
                  Use {derivedEnd} as end date
                </button>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Status</label>
              <select
                value={status}
                onChange={e => setStatus(e.target.value)}
                className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 focus:outline-none focus:border-brand-primary/40"
              >
                <option value="active">Active</option>
                <option value="terminated">Terminated</option>
                <option value="draft">Draft</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1.5">Notes</label>
              <textarea
                value={notes}
                onChange={e => setNotes(e.target.value)}
                rows={3}
                placeholder="Renewal conversations, pricing notes, etc."
                className="w-full px-3 py-2 rounded-lg text-sm bg-white/[0.03] border border-white/[0.08] text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-brand-primary/40 resize-none"
              />
            </div>
          </div>

          <div className="flex items-center justify-between px-5 py-4 border-t border-white/[0.08] bg-white/[0.02]">
            {mode === 'edit' ? (
              confirmDelete ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-red-400">Delete this contract?</span>
                  <button
                    onClick={handleDelete}
                    disabled={busy}
                    className="px-2.5 py-1 rounded text-[11px] font-medium bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30"
                  >
                    Yes, delete
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="px-2.5 py-1 rounded text-[11px] font-medium text-gray-400 hover:text-gray-200"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/20"
                >
                  <Trash2 size={13} />
                  Delete
                </button>
              )
            ) : (
              <div />
            )}
            <div className="flex gap-2">
              <button
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-400 hover:text-gray-200 hover:bg-white/[0.05]"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!canSave}
                className={clsx(
                  'px-4 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                  canSave
                    ? 'bg-brand-primary/20 text-brand-primary-light border-brand-primary/30 hover:bg-brand-primary/30'
                    : 'bg-white/[0.02] text-gray-600 border-white/[0.05] cursor-not-allowed'
                )}
              >
                {busy ? 'Saving...' : mode === 'create' ? 'Create' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
