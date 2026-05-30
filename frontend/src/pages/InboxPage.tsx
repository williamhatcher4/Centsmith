import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BriefcaseBusiness, CheckSquare, Inbox, Search, UserRoundCheck } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import type { Classification, Transaction } from '../types'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { Button, Card, Empty, Field, Input, PageHeader, Select, Skeleton, StatCard } from '../components/ui'

function fmtDate(d: string) {
  return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
function signedMoney(tx: Transaction) {
  return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}`
}

// Capped, cheap entrance stagger for table rows.
function rowDelay(i: number) {
  return i < 16 ? { animationDelay: `${Math.min(i, 12) * 25}ms` } : undefined
}
const ROW_ANIM = 'animate-[fadeInUp_360ms_var(--ease-out)_both]'

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-[var(--border)] bg-[var(--surface-muted)] px-1.5 py-0.5 font-mono text-[10px] font-semibold text-[var(--text-muted)]">
      {children}
    </kbd>
  )
}

export function InboxPage() {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkClass, setBulkClass] = useState<Classification | ''>('')
  const [search, setSearch] = useState('')
  const [focusedIndex, setFocusedIndex] = useState(0)
  const qc = useQueryClient()
  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ['transactions', 'unsorted'],
    queryFn: () => transactionsApi.list({ classification: 'unsorted', limit: 500 }),
  })

  const filtered = useMemo(
    () => transactions.filter((tx) => tx.description.toLowerCase().includes(search.trim().toLowerCase())),
    [transactions, search],
  )
  const selected = filtered.filter((tx) => selectedIds.has(tx.id))
  const total = transactions.reduce(
    (sum, tx) => sum + (tx.transaction_type === 'debit' ? tx.amount_cents : -tx.amount_cents),
    0,
  )

  const classify = useMutation({
    mutationFn: ({ ids, classification }: { ids: number[]; classification: Classification }) =>
      transactionsApi.bulkClassify(ids, classification),
    onSuccess: () => {
      setSelectedIds(new Set())
      setBulkClass('')
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
    },
  })

  function toggle(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  function toggleAll() {
    setSelectedIds(selectedIds.size === filtered.length ? new Set() : new Set(filtered.map((tx) => tx.id)))
  }
  function applyOne(tx: Transaction, classification: Classification) {
    classify.mutate({ ids: [tx.id], classification })
  }
  function applyBulk() {
    if (selected.length && bulkClass) classify.mutate({ ids: selected.map((tx) => tx.id), classification: bulkClass })
  }

  const safeFocus = filtered.length ? Math.min(focusedIndex, filtered.length - 1) : -1

  // Keyboard-driven triage. Refs keep the listener stable while always reading
  // the latest rows/cursor; shortcuts are ignored while typing in a field.
  const filteredRef = useRef(filtered)
  const focusedRef = useRef(safeFocus)
  useEffect(() => {
    filteredRef.current = filtered
  }, [filtered])
  useEffect(() => {
    focusedRef.current = safeFocus
  }, [safeFocus])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      const typing = !!el && ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)
      if (e.key === '/' && !typing) {
        e.preventDefault()
        document.getElementById('search')?.focus()
        return
      }
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return
      const rows = filteredRef.current
      if (!rows.length) return
      const idx = Math.max(0, Math.min(focusedRef.current, rows.length - 1))
      const tx = rows[idx]
      switch (e.key) {
        case 'j':
        case 'ArrowDown':
          e.preventDefault()
          setFocusedIndex(Math.min(idx + 1, rows.length - 1))
          break
        case 'k':
        case 'ArrowUp':
          e.preventDefault()
          setFocusedIndex(Math.max(idx - 1, 0))
          break
        case 'p':
          e.preventDefault()
          if (tx) classify.mutate({ ids: [tx.id], classification: 'personal' })
          break
        case 'w':
          e.preventDefault()
          if (tx) classify.mutate({ ids: [tx.id], classification: 'work' })
          break
        case 'x':
        case ' ':
          e.preventDefault()
          if (tx) toggle(tx.id)
          break
        case 'a':
          e.preventDefault()
          setSelectedIds(new Set(rows.map((r) => r.id)))
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // classify.mutate / toggle / setters are stable; refs supply fresh data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <PageHeader eyebrow="Triage" title="Inbox" subtitle="Sort imported transactions into Personal or Work" />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Open items" value={String(transactions.length)} animateTo={transactions.length} icon={<Inbox className="size-4" />} />
        <StatCard label="Net amount" value={formatMoney(total)} animateTo={total} format={(n) => formatMoney(Math.round(n))} gradient />
        <StatCard label="Selected" value={String(selected.length)} tone={selected.length ? 'accent' : 'neutral'} />
      </div>
      <Card variant="solid" padding="md" className="mb-5">
        <div className="grid gap-3 lg:grid-cols-[1fr_auto_auto] lg:items-end">
          <Field label="Search" htmlFor="search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-faint)]" />
              <Input id="search" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Description" />
            </div>
          </Field>
          <Field label="Bulk sort" htmlFor="bulk">
            <Select id="bulk" value={bulkClass} onChange={(e) => setBulkClass(e.target.value as Classification | '')} className="min-w-[190px]">
              <option value="">Choose type</option>
              <option value="personal">Personal</option>
              <option value="work">Work</option>
            </Select>
          </Field>
          <Button disabled={!selected.length || !bulkClass} loading={classify.isPending} leftIcon={<CheckSquare className="size-4" />} onClick={applyBulk}>
            Apply to {selected.length}
          </Button>
        </div>
      </Card>
      <p className="mb-3 hidden items-center gap-1.5 text-xs text-[var(--text-subtle)] md:flex">
        <span>Shortcuts:</span>
        <Kbd>J</Kbd><Kbd>K</Kbd><span>move</span>
        <Kbd>P</Kbd><span>personal</span>
        <Kbd>W</Kbd><span>work</span>
        <Kbd>X</Kbd><span>select</span>
        <Kbd>/</Kbd><span>search</span>
      </p>
      {isLoading ? (
        <Skeleton className="h-80" />
      ) : filtered.length === 0 ? (
        <Empty
          icon={<Inbox className="size-6" />}
          title={transactions.length ? 'No matches' : 'Inbox clear'}
          description={transactions.length ? 'Try another search.' : 'Every imported transaction is sorted.'}
        />
      ) : (
        <Card variant="solid" padding="none" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-strong)] bg-[var(--surface-muted)] text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--text-subtle)]">
                  <th className="w-1 px-4 py-3">
                    <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={filtered.length > 0 && selectedIds.size === filtered.length} onChange={toggleAll} />
                  </th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                  <th className="px-4 py-3">Sort</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((tx, i) => (
                  <tr
                    key={tx.id}
                    className={cn(
                      'border-b border-[var(--border)] transition-colors duration-150 last:border-0 hover:bg-[var(--surface-muted)]',
                      i < 16 && ROW_ANIM,
                      i === safeFocus && 'bg-[var(--accent-soft)] ring-1 ring-inset ring-[var(--accent-ring)]',
                    )}
                    style={rowDelay(i)}
                  >
                    <td className="px-4 py-3">
                      <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={selectedIds.has(tx.id)} onChange={() => toggle(tx.id)} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-[var(--text-subtle)]">{fmtDate(tx.transaction_date)}</td>
                    <td className="px-4 py-3 font-medium">{tx.description}</td>
                    <td className={cn('whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums', tx.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>
                      {signedMoney(tx)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <Button size="sm" variant="secondary" leftIcon={<UserRoundCheck className="size-4" />} onClick={() => applyOne(tx, 'personal')}>
                          Personal
                        </Button>
                        <Button size="sm" variant="secondary" leftIcon={<BriefcaseBusiness className="size-4" />} onClick={() => applyOne(tx, 'work')}>
                          Work
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
