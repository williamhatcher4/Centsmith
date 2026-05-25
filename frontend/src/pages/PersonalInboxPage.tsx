import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckSquare, Search, Tags } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import type { Transaction } from '../types'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { Button, Card, Empty, Field, Input, PageHeader, Select, Skeleton, StatCard } from '../components/ui'

const SPENDING_CATEGORIES = [
  'Groceries',
  'Dining',
  'Transportation',
  'Home',
  'Health',
  'Subscriptions',
  'Shopping',
  'Travel',
  'Entertainment',
  'Personal Care',
  'Gifts',
  'Other',
  'Transfer',
]
const INCOME_CATEGORIES = ['Income', 'Reimbursement']
const CREDIT_CATEGORIES = [...INCOME_CATEGORIES, ...SPENDING_CATEGORIES]

function categoriesFor(tx: Transaction) {
  return tx.transaction_type === 'credit' ? CREDIT_CATEGORIES : SPENDING_CATEGORIES
}

function fmtDate(d: string) {
  return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function signedMoney(tx: Transaction) {
  return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}`
}

export function PersonalInboxPage() {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [bulkCategory, setBulkCategory] = useState('')
  const [categoryById, setCategoryById] = useState<Record<number, string>>({})
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set())
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const qc = useQueryClient()

  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ['transactions', 'personal', 'uncategorized'],
    queryFn: () => transactionsApi.list({ classification: 'personal', personal_category: 'uncategorized', limit: 500 }),
  })

  const filtered = useMemo(
    () => transactions.filter((tx) => tx.description.toLowerCase().includes(search.trim().toLowerCase())),
    [transactions, search],
  )
  const selected = filtered.filter((tx) => selectedIds.has(tx.id))
  const total = transactions.reduce(
    (sum, tx) => sum + (tx.transaction_type === 'credit' ? tx.amount_cents : -tx.amount_cents),
    0,
  )
  const selectedTypes = new Set(selected.map((tx) => tx.transaction_type))
  const selectionType: 'credit' | 'debit' | 'mixed' | null =
    selected.length === 0 ? null : selectedTypes.size === 1 ? ([...selectedTypes][0] as 'credit' | 'debit') : 'mixed'
  const bulkCategoryOptions =
    selectionType === 'credit'
      ? CREDIT_CATEGORIES
      : selectionType === 'debit'
        ? SPENDING_CATEGORIES
        : selectionType === 'mixed'
          ? ['Transfer']
          : []

  const categorize = useMutation({
    mutationFn: ({ ids, category }: { ids: number[]; category: string }) => transactionsApi.bulkCategorizePersonal(ids, category),
    onMutate: ({ ids }) => {
      setError('')
      setSavingIds((prev) => new Set([...prev, ...ids]))
    },
    onSuccess: (_, variables) => {
      setSavingIds((prev) => {
        const next = new Set(prev)
        variables.ids.forEach((id) => next.delete(id))
        return next
      })
      setCategoryById((prev) => {
        const next = { ...prev }
        variables.ids.forEach((id) => delete next[id])
        return next
      })
      setSelectedIds(new Set())
      setBulkCategory('')
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
      qc.invalidateQueries({ queryKey: ['income'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (err, variables) => {
      setSavingIds((prev) => {
        const next = new Set(prev)
        variables.ids.forEach((id) => next.delete(id))
        return next
      })
      setError(err instanceof Error ? err.message : 'Category save failed')
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

  function applyOne(tx: Transaction, category: string) {
    const nextCategory = category.trim()
    if (nextCategory) categorize.mutate({ ids: [tx.id], category: nextCategory })
  }

  function applyBulk() {
    if (selected.length && bulkCategory) categorize.mutate({ ids: selected.map((tx) => tx.id), category: bulkCategory })
  }

  return (
    <div>
      <PageHeader title="Personal Inbox" subtitle="Categorize personal spending after it has been sorted from the main inbox" />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Open personal items" value={String(transactions.length)} icon={<Tags className="size-4" />} />
        <StatCard label="Uncategorized total" value={formatMoney(total)} />
        <StatCard label="Selected" value={String(selected.length)} tone={selected.length ? 'accent' : 'neutral'} />
      </div>

      <Card variant="solid" padding="md" className="mb-5">
        <div className="grid gap-3 lg:grid-cols-[1fr_210px_auto] lg:items-end">
          <Field label="Search" htmlFor="personal-search" className="mb-0">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-faint)]" />
              <Input id="personal-search" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Description" />
            </div>
          </Field>
          <Field label="Bulk category" htmlFor="bulk-category" className="mb-0">
            <Select id="bulk-category" value={bulkCategory} disabled={!selectionType} onChange={(e) => setBulkCategory(e.target.value)}>
              <option value="">{selectionType ? 'Choose category' : 'Select rows first'}</option>
              {bulkCategoryOptions.map((category) => <option key={category} value={category}>{category}</option>)}
            </Select>
          </Field>
          <Button disabled={!selected.length || !bulkCategory || !selectionType} loading={categorize.isPending} leftIcon={<CheckSquare className="size-4" />} onClick={applyBulk}>
            Apply to {selected.length}
          </Button>
        </div>
        {error && <p className="mt-3 text-sm font-medium text-[var(--danger)]">{error}</p>}
      </Card>

      {isLoading ? (
        <Skeleton className="h-80" />
      ) : filtered.length === 0 ? (
        <Empty icon={<Tags className="size-6" />} title={transactions.length ? 'No matches' : 'Personal inbox clear'} description={transactions.length ? 'Try another search.' : 'Every personal transaction has a category.'} />
      ) : (
        <Card variant="solid" padding="none" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] text-left text-xs font-semibold uppercase text-[var(--text-subtle)]">
                  <th className="w-1 px-4 py-3"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={filtered.length > 0 && selectedIds.size === filtered.length} onChange={toggleAll} /></th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3 text-right">Amount</th>
                  <th className="px-4 py-3">Category</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((tx) => {
                  const category = categoryById[tx.id] ?? ''
                  return (
                    <tr key={tx.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-muted)]">
                      <td className="px-4 py-3"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={selectedIds.has(tx.id)} onChange={() => toggle(tx.id)} /></td>
                      <td className="whitespace-nowrap px-4 py-3 text-xs text-[var(--text-subtle)]">{fmtDate(tx.transaction_date)}</td>
                      <td className="px-4 py-3 font-medium">{tx.description}</td>
                      <td className={cn('whitespace-nowrap px-4 py-3 text-right font-bold tabular-nums', tx.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>{signedMoney(tx)}</td>
                      <td className="min-w-[180px] px-4 py-3">
                        <Select
                          aria-label={`Category for ${tx.description}`}
                          value={category}
                          disabled={savingIds.has(tx.id)}
                          onChange={(e) => {
                            const val = e.target.value
                            setCategoryById((prev) => ({ ...prev, [tx.id]: val }))
                            if (val) applyOne(tx, val)
                          }}
                        >
                          <option value="">Choose</option>
                          {categoriesFor(tx).map((c) => <option key={c} value={c}>{c}</option>)}
                        </Select>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
