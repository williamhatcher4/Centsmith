import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  LogOut,
  Moon,
  Plus,
  Receipt,
  Search,
  Sun,
  Upload,
  type LucideIcon,
} from 'lucide-react'
import type { NavLinkDef } from '../constants/nav'
import { useTheme } from './ui/theme'
import { cn } from '../utils/cn'

interface Command {
  id: string
  label: string
  group: 'Go to' | 'Actions'
  icon: LucideIcon
  keywords?: string
  run: () => void
}

interface Props {
  /** Render only while open so each open starts from fresh state. */
  onClose: () => void
  links: NavLinkDef[]
  onLogout: () => void
}

export function CommandPalette({ onClose, links, onLogout }: Props) {
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const commands = useMemo<Command[]>(() => {
    const run = (fn: () => void) => () => {
      onClose()
      fn()
    }
    const nav: Command[] = links.map((l) => ({
      id: `nav:${l.to}`,
      label: l.label,
      group: 'Go to',
      icon: l.icon,
      run: run(() => navigate(l.to)),
    }))
    const actions: Command[] = [
      {
        id: 'action:add',
        label: 'Add transaction',
        group: 'Actions',
        icon: Plus,
        keywords: 'new manual create entry',
        run: run(() => navigate('/transactions?action=add')),
      },
      {
        id: 'action:import',
        label: 'Import statement',
        group: 'Actions',
        icon: Upload,
        keywords: 'csv upload bank',
        run: run(() => navigate('/transactions?action=import')),
      },
      {
        id: 'action:reimbursement',
        label: 'Awaiting reimbursement',
        group: 'Actions',
        icon: Receipt,
        keywords: 'work expensed owed money',
        run: run(() => navigate('/transactions?classification=work&expensed=unexpensed')),
      },
      {
        id: 'action:theme',
        label: theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode',
        group: 'Actions',
        icon: theme === 'dark' ? Sun : Moon,
        keywords: 'theme dark light appearance',
        run: run(toggle),
      },
      {
        id: 'action:logout',
        label: 'Sign out',
        group: 'Actions',
        icon: LogOut,
        keywords: 'logout exit',
        run: run(onLogout),
      },
    ]
    return [...nav, ...actions]
  }, [links, navigate, theme, toggle, onLogout, onClose])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((c) => `${c.label} ${c.keywords ?? ''}`.toLowerCase().includes(q))
  }, [commands, query])

  // Focus the search input when the palette mounts (it only mounts while open).
  useEffect(() => {
    const id = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [])

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => (filtered.length ? (i + 1) % filtered.length : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => (filtered.length ? (i - 1 + filtered.length) % filtered.length : 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      filtered[activeIndex]?.run()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose()
    }
  }

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-[120] flex items-start justify-center px-4 pt-[12vh]"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="absolute inset-0 bg-black/45 backdrop-blur-md animate-[fadeIn_160ms_var(--ease-out)]" />
      <div
        className="relative w-full max-w-lg overflow-hidden rounded-[var(--radius-xl)] border border-[var(--border-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)] ring-1 ring-inset ring-white/10 backdrop-blur-2xl animate-[slideUp_220ms_var(--ease-drawer)]"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-[var(--border)] px-4">
          <Search className="size-4 shrink-0 text-[var(--text-faint)]" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setActiveIndex(0)
            }}
            onKeyDown={onKeyDown}
            placeholder="Search pages and actions…"
            aria-label="Search pages and actions"
            className="w-full bg-transparent py-3.5 text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-faint)]"
          />
          <kbd className="hidden shrink-0 rounded border border-[var(--border)] bg-[var(--surface-muted)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--text-subtle)] sm:block">
            ESC
          </kbd>
        </div>
        <ul className="max-h-[52vh] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-[var(--text-subtle)]">No matching commands</li>
          ) : (
            filtered.map((c, i) => {
              const Icon = c.icon
              const active = i === activeIndex
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    onMouseEnter={() => setActiveIndex(i)}
                    onClick={c.run}
                    className={cn(
                      'flex w-full items-center gap-3 rounded-[10px] px-3 py-2.5 text-left text-sm transition-colors',
                      active ? 'bg-[var(--accent-soft)] text-[var(--text)]' : 'text-[var(--text-muted)]',
                    )}
                  >
                    <Icon className={cn('size-[18px] shrink-0', active ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)]')} />
                    <span className="flex-1 font-medium">{c.label}</span>
                    <span className="text-[10px] uppercase tracking-wide text-[var(--text-faint)]">{c.group}</span>
                    {active && <ArrowRight className="size-3.5 text-[var(--accent)]" />}
                  </button>
                </li>
              )
            })
          )}
        </ul>
      </div>
    </div>,
    document.body,
  )
}
