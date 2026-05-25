import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { BarChart3, Download, Inbox, LogOut, ReceiptText, Tags, TrendingDown } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { authApi } from '../api/auth'
import { useAppStore } from '../store/useAppStore'
import { Avatar, IconButton, ThemeToggle } from './ui'
import { cn } from '../utils/cn'

const links: { to: string; label: string; icon: LucideIcon }[] = [
  { to: '/', label: 'Dashboard', icon: BarChart3 },
  { to: '/inbox', label: 'Inbox', icon: Inbox },
  { to: '/personal-inbox', label: 'Personal Inbox', icon: Tags },
  { to: '/transactions', label: 'Transactions', icon: ReceiptText },
  { to: '/spending', label: 'Spending', icon: TrendingDown },
  { to: '/exports', label: 'Exports', icon: Download },
]

function BrandMark() {
  return <span className="flex size-8 items-center justify-center rounded-[8px] bg-[var(--accent)] text-sm font-black text-white">CS</span>
}

export function AppShell() {
  const { user, setUser } = useAppStore()
  const navigate = useNavigate()

  async function logout() {
    await authApi.logout()
    setUser(null)
    navigate('/login')
  }

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-[244px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] backdrop-blur-xl md:flex">
        <div className="px-5 pb-5 pt-6">
          <div className="flex items-center gap-2.5">
            <BrandMark />
            <span className="text-base font-bold text-[var(--text)]">Centsmith</span>
          </div>
        </div>
        <nav className="flex-1 px-3" aria-label="Primary">
          <ul className="space-y-1">
            {links.map(({ to, label, icon: Icon }) => (
              <li key={to}>
                <NavLink to={to} end={to === '/'} className={({ isActive }) => cn('flex items-center gap-2.5 rounded-[8px] px-3 py-2 text-sm font-medium transition-colors', isActive ? 'bg-[var(--accent-soft)] text-[var(--accent)]' : 'text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]')}>
                  <Icon className="size-[18px]" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="border-t border-[var(--border)] p-3">
          <div className="flex items-center gap-2.5 rounded-[8px] px-2 py-2">
            <Avatar name={user?.display_name} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-[var(--text)]">{user?.display_name}</div>
              <div className="truncate text-xs text-[var(--text-subtle)]">{user?.username}</div>
            </div>
          </div>
          <div className="mt-2 flex justify-between">
            <ThemeToggle size="sm" />
            <IconButton aria-label="Sign out" size="sm" onClick={logout} icon={<LogOut className="size-4" />} />
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-4 backdrop-blur-xl md:hidden">
          <div className="flex items-center gap-2.5"><BrandMark /><span className="font-bold">Centsmith</span></div>
          <ThemeToggle size="sm" />
        </header>
        <main className="flex-1 px-4 py-6 md:px-8 lg:px-10">
          <div className="mx-auto max-w-[1180px]"><Outlet /></div>
        </main>
        <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-[var(--border)] bg-[var(--surface-strong)] pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-xl md:hidden">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => cn('flex flex-col items-center gap-1 px-1 py-2 text-[10px] font-semibold', isActive ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)]')}>
              <Icon className="size-5" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>
      </div>
    </div>
  )
}
