import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { settingsApi } from '../api/settings'
import { useAppStore } from '../store/useAppStore'
import { Avatar, IconButton, ThemeToggle } from './ui'
import { cn } from '../utils/cn'
import { NAV_LINKS, visibleLinks } from '../constants/nav'

function BrandMark() {
  return <span className="flex size-8 items-center justify-center rounded-[8px] bg-[var(--accent)] text-sm font-black text-white">CS</span>
}

export function AppShell() {
  const { user, setUser } = useAppStore()
  const navigate = useNavigate()
  const location = useLocation()
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.get(),
    staleTime: 60_000,
  })
  const hiddenPages = settings?.hidden_pages ?? []
  const links = visibleLinks(hiddenPages)

  async function logout() {
    await authApi.logout()
    setUser(null)
    navigate('/login')
  }

  if (hiddenPages.includes(location.pathname)) {
    const fallback = links[0]?.to ?? NAV_LINKS[0].to
    return <Navigate to={fallback} replace />
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
        <nav
          className="fixed inset-x-0 bottom-0 z-40 grid border-t border-[var(--border)] bg-[var(--surface-strong)] pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-xl md:hidden"
          style={{ gridTemplateColumns: `repeat(${links.length}, minmax(0, 1fr))` }}
          aria-label="Primary mobile"
        >
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
