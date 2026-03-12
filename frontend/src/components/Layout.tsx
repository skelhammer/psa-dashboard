import { NavLink, Outlet } from 'react-router-dom'
import { useSyncStatus, useTriggerSync } from '../api/hooks'
import clsx from 'clsx'

const navItems = [
  { to: '/', label: 'Overview', icon: '📊' },
  { to: '/manage-to-zero', label: 'Manage to Zero', icon: '🎯' },
  { to: '/work-queue', label: 'Work Queue', icon: '📋' },
  { to: '/technicians', label: 'Technicians', icon: '👥' },
  { to: '/billing', label: 'Billing Audit', icon: '💰' },
]

export default function Layout() {
  const { data: syncStatus } = useSyncStatus()
  const triggerSync = useTriggerSync()

  const lastSync = syncStatus?.last_sync
    ? new Date(syncStatus.last_sync).toLocaleTimeString()
    : 'Never'

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-60 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
        {/* Logo */}
        <div className="p-5 border-b border-gray-800">
          <h1 className="text-lg font-bold tracking-tight">
            <span className="text-brand-gold">PSA</span>
            <span className="text-gray-400 font-normal ml-1.5">Dashboard</span>
          </h1>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                  isActive
                    ? 'bg-brand-gold/10 text-brand-gold border border-brand-gold/20'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                )
              }
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Provider info */}
        <div className="p-4 border-t border-gray-800 text-xs text-gray-600">
          Data source: {syncStatus?.provider || '...'}
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 bg-gray-900/50 border-b border-gray-800 flex items-center justify-between px-6 shrink-0">
          <div />
          <div className="flex items-center gap-4">
            <span className="text-xs text-gray-500">
              Last synced: {lastSync}
              {syncStatus?.is_syncing && (
                <span className="ml-2 text-brand-gold animate-pulse">Syncing...</span>
              )}
            </span>
            <button
              onClick={() => triggerSync.mutate()}
              disabled={triggerSync.isPending || syncStatus?.is_syncing}
              className={clsx(
                'px-3 py-1.5 rounded-md text-xs font-medium transition-all',
                triggerSync.isPending || syncStatus?.is_syncing
                  ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                  : 'bg-brand-gold/10 text-brand-gold border border-brand-gold/30 hover:bg-brand-gold/20'
              )}
            >
              {triggerSync.isPending ? 'Syncing...' : 'Sync Now'}
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
