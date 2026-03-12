import { NavLink, Outlet } from 'react-router-dom'
import { useSyncStatus, useTriggerSync, useTriggerFullSync } from '../api/hooks'
import {
  LayoutDashboard, Target, ListOrdered, Users, Receipt, Building2,
  RefreshCw, RefreshCcw, Zap
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/manage-to-zero', label: 'Manage to Zero', icon: Target },
  { to: '/work-queue', label: 'Work Queue', icon: ListOrdered },
  { to: '/technicians', label: 'Technicians', icon: Users },
  { to: '/billing', label: 'Billing Audit', icon: Receipt },
  { to: '/clients', label: 'Client Health', icon: Building2 },
]

export default function Layout() {
  const { data: syncStatus } = useSyncStatus()
  const triggerSync = useTriggerSync()
  const triggerFullSync = useTriggerFullSync()
  const anySyncing = triggerSync.isPending || triggerFullSync.isPending || syncStatus?.is_syncing

  const lastSync = syncStatus?.last_sync
    ? new Date(syncStatus.last_sync).toLocaleTimeString()
    : 'Never'

  return (
    <div className="flex h-screen overflow-hidden bg-[#09090B]">
      {/* Sidebar */}
      <aside className="w-[220px] flex flex-col shrink-0 border-r border-white/[0.06] bg-[#09090B]">
        {/* Logo */}
        <div className="px-5 py-5 border-b border-white/[0.06]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/20">
              <Zap size={16} className="text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-white">PSA Dashboard</h1>
              <p className="text-[10px] text-gray-500 font-medium">Service Metrics</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems.map(item => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  clsx(
                    'group flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150',
                    isActive
                      ? 'bg-brand-primary/10 text-brand-primary-light'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.04]'
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
        <div className="px-5 py-3 border-t border-white/[0.06]">
          <p className="text-[10px] text-gray-600 font-medium">
            {syncStatus?.provider || '...'}
          </p>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-12 border-b border-white/[0.06] flex items-center justify-end px-6 shrink-0 bg-[#09090B]/80 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-[11px] text-gray-500">
              <div className={clsx(
                'w-1.5 h-1.5 rounded-full',
                syncStatus?.is_syncing ? 'bg-blue-400 animate-pulse' : 'bg-emerald-400'
              )} />
              {syncStatus?.is_syncing ? 'Syncing...' : `Synced ${lastSync}`}
            </div>
            <div className="w-px h-4 bg-white/[0.06]" />
            <button
              onClick={() => triggerSync.mutate()}
              disabled={anySyncing}
              className={clsx(
                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all duration-150',
                anySyncing
                  ? 'text-gray-600 cursor-not-allowed'
                  : 'text-gray-400 hover:text-brand-primary hover:bg-brand-primary/10'
              )}
            >
              <RefreshCw size={12} className={anySyncing ? 'animate-spin' : ''} />
              Sync
            </button>
            <button
              onClick={() => triggerFullSync.mutate()}
              disabled={anySyncing}
              className={clsx(
                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition-all duration-150',
                anySyncing
                  ? 'text-gray-600 cursor-not-allowed'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]'
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
