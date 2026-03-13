import { NavLink, Outlet } from 'react-router-dom'
import { useSyncStatus, useTriggerSync, useTriggerFullSync } from '../api/hooks'
import {
  LayoutDashboard, Target, ListOrdered, Users, Receipt, Building2,
  RefreshCw, RefreshCcw, Zap, FileBarChart
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/executive', label: 'Executive Report', icon: FileBarChart },
  { to: '/manage-to-zero', label: 'Manage to Zero', icon: Target },
  { to: '/work-queue', label: 'Work Queue', icon: ListOrdered },
  { to: '/technicians', label: 'Technicians', icon: Users },
  { to: '/billing', label: 'Billing Audit', icon: Receipt },
  { to: '/clients', label: 'Client Health', icon: Building2 },
]

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export default function Layout() {
  const { data: syncStatus } = useSyncStatus()
  const triggerSync = useTriggerSync()
  const triggerFullSync = useTriggerFullSync()
  const anySyncing = triggerSync.isPending || triggerFullSync.isPending || syncStatus?.is_syncing

  const lastSync = syncStatus?.last_sync
    ? timeAgo(syncStatus.last_sync)
    : 'Never'

  return (
    <div className="flex h-screen overflow-hidden bg-[#09090B]">
      {/* Sidebar */}
      <aside className="w-[220px] flex flex-col shrink-0 border-r border-white/[0.08] bg-[#0C0C0E]">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-white/[0.08]">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/25">
              <Zap size={17} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-white">PSA Dashboard</h1>
              <p className="text-[10px] text-gray-500 font-medium">Service Metrics</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(item => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  clsx(
                    'group flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-150',
                    isActive
                      ? 'bg-brand-primary/[0.12] text-brand-primary-light border border-brand-primary/[0.15]'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.05] border border-transparent'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon size={18} className={clsx(
                      'transition-colors duration-150',
                      isActive ? 'text-brand-primary' : 'text-gray-600 group-hover:text-gray-400'
                    )} />
                    {item.label}
                  </>
                )}
              </NavLink>
            )
          })}
        </nav>

        {/* Provider info */}
        <div className="px-4 py-3 border-t border-white/[0.08]">
          <p className="text-[10px] text-gray-600 font-medium">
            {syncStatus?.provider || '...'}
          </p>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-12 border-b border-white/[0.08] flex items-center justify-end px-6 shrink-0 bg-[#0C0C0E]/80 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-[11px] text-gray-500 font-medium">
              <div className={clsx(
                'w-1.5 h-1.5 rounded-full',
                syncStatus?.is_syncing ? 'bg-blue-400 animate-pulse' : 'bg-emerald-400'
              )} />
              {syncStatus?.is_syncing ? 'Syncing...' : `Synced ${lastSync}`}
            </div>
            <div className="w-px h-4 bg-white/[0.08]" />
            <button
              onClick={() => triggerSync.mutate()}
              disabled={anySyncing}
              className={clsx(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-150',
                anySyncing
                  ? 'text-gray-600 cursor-not-allowed'
                  : 'text-gray-400 hover:text-brand-primary hover:bg-brand-primary/10 border border-transparent hover:border-brand-primary/20'
              )}
            >
              <RefreshCw size={12} className={anySyncing ? 'animate-spin' : ''} />
              Sync
            </button>
            <button
              onClick={() => triggerFullSync.mutate()}
              disabled={anySyncing}
              className={clsx(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-150',
                anySyncing
                  ? 'text-gray-600 cursor-not-allowed'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.06] border border-transparent hover:border-white/[0.1]'
              )}
            >
              <RefreshCcw size={12} />
              Full
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
