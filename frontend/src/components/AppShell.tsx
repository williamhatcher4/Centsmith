import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LogOut, Search } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { authApi } from '../api/auth'
import { settingsApi } from '../api/settings'
import { useAppStore } from '../store/useAppStore'
import { Avatar, IconButton, ThemeToggle, AuroraBackground } from './ui'
import { cn } from '../utils/cn'
import { NAV_LINKS, visibleLinks } from '../constants/nav'
import { useReducedMotion } from '../hooks/useReducedMotion'
import { CommandPalette } from './CommandPalette'

function BrandMark() {
  return (
    <span className="relative flex size-8 items-center justify-center rounded-[10px] bg-[image:var(--grad-brand)] text-white shadow-[var(--shadow-glow)] ring-1 ring-inset ring-white/25">
      <span className="font-display text-[15px] font-bold leading-none">¢</span>
    </span>
  )
}

function isLinkActive(pathname: string, to: string) {
  if (to === '/') return pathname === '/'
  return pathname === to || pathname.startsWith(to + '/')
}

export function AppShell() {
  const { user, setUser } = useAppStore()
  const navigate = useNavigate()
  const location = useLocation()
  const reduced = useReducedMotion()
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.get(),
    staleTime: 60_000,
  })
  const hiddenPages = settings?.hidden_pages ?? []
  const links = visibleLinks(hiddenPages)
  const [paletteOpen, setPaletteOpen] = useState(false)

  // Global ⌘K / Ctrl+K toggles the command palette.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Sliding active-nav indicator (desktop sidebar).
  const itemRefs = useRef<(HTMLLIElement | null)[]>([])
  const [indicator, setIndicator] = useState<{ top: number; height: number } | null>(null)
  const activeIndex = links.findIndex((l) => isLinkActive(location.pathname, l.to))

  useLayoutEffect(() => {
    const el = itemRefs.current[activeIndex]
    if (el && el.offsetHeight > 0) {
      setIndicator({ top: el.offsetTop, height: el.offsetHeight })
    } else {
      setIndicator(null)
    }
  }, [activeIndex, links.length])

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
    <div className="relative flex min-h-screen">
      <AuroraBackground />
      <aside className="sticky top-0 hidden h-screen w-[244px] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] backdrop-blur-xl md:flex">
        <div className="px-5 pb-5 pt-6">
          <div className="flex items-center gap-2.5">
            <BrandMark />
            <span className="font-display text-base font-bold tracking-tight text-[var(--text)]">Centsmith</span>
          </div>
        </div>
        <nav className="flex-1 px-3" aria-label="Primary">
          <ul className="relative space-y-1">
            {indicator && indicator.height > 0 && (
              <span
                aria-hidden="true"
                className="absolute inset-x-0 rounded-[10px] bg-[var(--accent-soft)] ring-1 ring-inset ring-[var(--accent-ring)]"
                style={{
                  top: indicator.top,
                  height: indicator.height,
                  transition: reduced
                    ? undefined
                    : 'top 240ms var(--ease-out), height 240ms var(--ease-out)',
                }}
              />
            )}
            {links.map(({ to, label, icon: Icon }, i) => (
              <li
                key={to}
                ref={(el) => {
                  itemRefs.current[i] = el
                }}
              >
                <NavLink
                  to={to}
                  end={to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'relative z-10 flex items-center gap-2.5 rounded-[10px] px-3 py-2 text-sm font-medium transition-[color,transform] duration-150 ease-[var(--ease-out)] active:scale-[0.98]',
                      isActive
                        ? 'text-[var(--accent)]'
                        : 'text-[var(--text-muted)] hover:text-[var(--text)]',
                    )
                  }
                >
                  <Icon className="size-[18px]" />
                  {label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className="px-3 pb-2">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex w-full items-center gap-2.5 rounded-[10px] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-subtle)] transition-colors hover:text-[var(--text)]"
          >
            <Search className="size-[18px]" />
            <span className="flex-1 text-left">Search…</span>
            <kbd className="rounded border border-[var(--border)] bg-[var(--surface-solid)] px-1.5 py-0.5 text-[10px] font-semibold">⌘K</kbd>
          </button>
        </div>
        <div className="border-t border-[var(--border)] p-3">
          <div className="flex items-center gap-2.5 rounded-[10px] px-2 py-2">
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
      <div className="relative flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)] px-4 backdrop-blur-xl md:hidden">
          <div className="flex items-center gap-2.5">
            <BrandMark />
            <span className="font-display font-bold tracking-tight">Centsmith</span>
          </div>
          <ThemeToggle size="sm" />
        </header>
        <main className="flex-1 px-4 py-6 md:px-8 lg:px-10">
          <div className="mx-auto max-w-[1180px]">
            <div key={location.pathname} className="animate-[fadeInUp_320ms_var(--ease-out)]">
              <Outlet />
            </div>
          </div>
        </main>
        <nav
          className="fixed inset-x-0 bottom-0 z-40 grid border-t border-[var(--border)] bg-[var(--surface-strong)] pb-[env(safe-area-inset-bottom,0px)] backdrop-blur-xl md:hidden"
          style={{ gridTemplateColumns: `repeat(${links.length}, minmax(0, 1fr))` }}
          aria-label="Primary mobile"
        >
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                cn(
                  'relative flex flex-col items-center gap-1 px-1 py-2 text-[10px] font-semibold transition-[color,transform] duration-150 ease-[var(--ease-out)] active:scale-95',
                  isActive ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)]',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-x-4 top-0 h-[3px] rounded-b-full bg-[image:var(--grad-brand)]"
                    />
                  )}
                  <Icon className="size-5" />
                  <span className="truncate">{label}</span>
                </>
              )}
            </NavLink>
          ))}
        </nav>
      </div>
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} links={links} onLogout={logout} />}
    </div>
  )
}
