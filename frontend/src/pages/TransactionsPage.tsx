import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Landmark, Pencil, Plus, Trash2, Upload, X } from 'lucide-react'
import { cardsApi } from '../api/cards'
import { transactionsApi } from '../api/transactions'
import type { ClassificationFilter, ExpensedFilter, Transaction, TransactionCreatePayload, TransactionType } from '../types'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { patchTxCache, type TxCache } from '../utils/txCache'
import { invalidateAnalytics, invalidateLedger } from '../utils/queryInvalidation'
import { AddTransactionModal } from '../components/AddTransactionModal'
import { EditTransactionModal } from '../components/EditTransactionModal'
import { ImportModal } from '../components/ImportModal'
import { Badge, Button, Card, Empty, Field, Input, PageHeader, Select, Skeleton } from '../components/ui'
import { useConfirm } from '../components/ui/confirm-context'
import { useToast } from '../components/ui/toast-context'
import { useCategories } from '../hooks/useCategories'

const PAGE_SIZE = 200

function fmtDate(d: string) { return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
function signedMoney(tx: Transaction) { return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}` }

function rowDelay(i: number) {
  return i < 16 ? { animationDelay: `${Math.min(i, 12) * 25}ms` } : undefined
}
const ROW_ANIM = 'animate-[fadeInUp_360ms_var(--ease-out)_both]'

type TypeFilter = TransactionType | 'all'

function readClassificationParam(value: string | null): ClassificationFilter {
  return value === 'personal' || value === 'work' || value === 'unsorted' ? value : 'all'
}
function readTypeParam(value: string | null): TypeFilter {
  return value === 'debit' || value === 'credit' ? value : 'all'
}
function readExpensedParam(value: string | null): ExpensedFilter {
  return value === 'expensed' || value === 'unexpensed' ? value : 'all'
}
function readDateParam(value: string | null): string {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : ''
}

export function TransactionsPage() {
  const [searchParams] = useSearchParams()
  const initialAction = searchParams.get('action')
  const [importMode, setImportMode] = useState<'card' | 'checking' | null>(initialAction === 'import' ? 'card' : null)
  const [showAddModal, setShowAddModal] = useState(initialAction === 'add')
  const [editingTx, setEditingTx] = useState<Transaction | null>(null)
  const [classification, setClassification] = useState<ClassificationFilter>(() => readClassificationParam(searchParams.get('classification')))
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(() => readTypeParam(searchParams.get('transaction_type')))
  const [expensed, setExpensed] = useState<ExpensedFilter>(() => readExpensedParam(searchParams.get('expensed')))
  // '' means "no category filter" — the sentinel must not collide with a real
  // category name (a user can literally create a category called "all").
  const [personalCategory, setPersonalCategory] = useState(() => searchParams.get('personal_category') || '')
  const [startDate, setStartDate] = useState(() => readDateParam(searchParams.get('start_date')))
  const [endDate, setEndDate] = useState(() => readDateParam(searchParams.get('end_date')))
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [assignCardId, setAssignCardId] = useState('')
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const { all: allCategories } = useCategories()
  const { data: cards = [] } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.list() })
  const showExpensed = classification === 'work'
  const activeExpensed = showExpensed ? expensed : 'all'
  const showPersonalCategory = classification === 'personal'
  const activePersonalCategory = showPersonalCategory ? personalCategory : ''

  const queryKey = ['transactions', classification, typeFilter, activeExpensed, activePersonalCategory, startDate, endDate]

  const { data, isLoading, hasNextPage, fetchNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => transactionsApi.list({ classification, transaction_type: typeFilter, expensed: activeExpensed, personal_category: activePersonalCategory || undefined, start_date: startDate, end_date: endDate, limit: PAGE_SIZE, skip: pageParam }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) => lastPage.next_skip ?? undefined,
  })
  const transactions = data?.pages.flatMap((p) => p.items) ?? []
  const total = data?.pages[0]?.total ?? 0

  const updateExpensed = useMutation({
    mutationFn: ({ id, next }: { id: number; next: boolean }) => transactionsApi.update(id, { expensed: next }),
    onSuccess: (updated) => {
      qc.setQueriesData<TxCache>({ queryKey: ['transactions'] }, (current) => patchTxCache(current, (tx) => (tx.id === updated.id ? updated : tx)))
      qc.invalidateQueries({ queryKey: ['transactions'] })
      // Expensed status drives the Dashboard "Awaiting reimbursement" figure.
      invalidateAnalytics(qc)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => transactionsApi.deleteTransaction(id),
    onSuccess: (deleted) => {
      qc.setQueriesData<TxCache>({ queryKey: ['transactions'] }, (current) => patchTxCache(current, (tx) => (tx.id === deleted.id ? null : tx)))
      invalidateLedger(qc)
      invalidateAnalytics(qc)
      if (deleted.is_manual) {
        toast.success('Transaction deleted', {
          action: {
            label: 'Undo',
            onClick: () => {
              const payload: TransactionCreatePayload = {
                transaction_date: deleted.transaction_date,
                description: deleted.description,
                amount_cents: deleted.amount_cents,
                transaction_type: deleted.transaction_type,
                classification: deleted.classification,
                personal_category: deleted.personal_category,
                expensed: deleted.expensed,
              }
              // The delete invalidated ledger + analytics; recreating the row
              // must do the same or aggregates stay in the deleted state.
              transactionsApi.createManual(payload)
                .then(() => {
                  invalidateLedger(qc)
                  invalidateAnalytics(qc)
                })
                .catch((err: Error) => toast.error(err.message))
            },
          },
        })
      } else {
        toast.success('Transaction deleted')
      }
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const bulkAssignCard = useMutation({
    mutationFn: ({ ids, cardId }: { ids: number[]; cardId: number | null }) => transactionsApi.bulkAssignCard(ids, cardId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['statement'] })
      setSelectedIds(new Set())
      setAssignCardId('')
      toast.success(`Updated ${res.updated} transaction${res.updated === 1 ? '' : 's'}`)
    },
    onError: (err: Error) => toast.error(err.message),
  })

  async function handleDelete(tx: Transaction) {
    const ok = await confirm({
      title: 'Delete transaction',
      message: `Delete "${tx.description}"? This cannot be undone from this dialog${tx.is_manual ? ' — but you can Undo via the notification' : ''}.`,
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (ok) deleteMutation.mutate(tx.id)
  }

  function toggleSelected(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const allPageSelected = transactions.length > 0 && transactions.every((tx) => selectedIds.has(tx.id))
  function toggleSelectAll() {
    setSelectedIds((prev) => {
      if (transactions.every((tx) => prev.has(tx.id))) {
        const next = new Set(prev)
        transactions.forEach((tx) => next.delete(tx.id))
        return next
      }
      const next = new Set(prev)
      transactions.forEach((tx) => next.add(tx.id))
      return next
    })
  }

  const hasFilter = classification !== 'all' || typeFilter !== 'all' || activeExpensed !== 'all' || activePersonalCategory || startDate || endDate

  return <div>
    <PageHeader
      eyebrow="Ledger"
      title="Transactions"
      subtitle="All account activity — imported and manual"
      actions={
        <div className="flex gap-2">
          <Button leftIcon={<Plus className="size-4" />} onClick={() => setShowAddModal(true)}>Add</Button>
          <Button leftIcon={<Upload className="size-4" />} onClick={() => setImportMode('card')}>Import</Button>
          <Button variant="secondary" leftIcon={<Landmark className="size-4" />} onClick={() => setImportMode('checking')}>Import Checking</Button>
        </div>
      }
    />
    <Card variant="solid" padding="sm" className="mb-5">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto_auto_auto] sm:items-end">
        <Field label="Sort" htmlFor="class">
          <Select id="class" value={classification} onChange={(e) => { const next = e.target.value as ClassificationFilter; setClassification(next); if (next !== 'work') setExpensed('all'); if (next !== 'personal') setPersonalCategory('') }}>
            <option value="all">All</option>
            <option value="unsorted">Unsorted</option>
            <option value="personal">Personal</option>
            <option value="work">Work</option>
          </Select>
        </Field>
        <Field label="Type" htmlFor="tx-type">
          <Select id="tx-type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as TypeFilter)}>
            <option value="all">All</option>
            <option value="debit">Debits</option>
            <option value="credit">Credits</option>
          </Select>
        </Field>
        {showExpensed && <Field label="Expensed" htmlFor="expensed"><Select id="expensed" value={expensed} onChange={(e) => setExpensed(e.target.value as ExpensedFilter)}><option value="all">All work</option><option value="unexpensed">Needs expensing</option><option value="expensed">Expensed</option></Select></Field>}
        {showPersonalCategory && <Field label="Category" htmlFor="personal-cat"><Select id="personal-cat" value={personalCategory} onChange={(e) => setPersonalCategory(e.target.value)}><option value="">All categories</option><option value="uncategorized">Uncategorized</option>{allCategories.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>}
        <Field label="From" htmlFor="from"><Input id="from" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></Field>
        <Field label="To" htmlFor="to"><Input id="to" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></Field>
        {hasFilter && <Button variant="ghost" leftIcon={<X className="size-4" />} onClick={() => { setClassification('all'); setTypeFilter('all'); setExpensed('all'); setPersonalCategory(''); setStartDate(''); setEndDate('') }}>Clear</Button>}
      </div>
    </Card>

    {selectedIds.size > 0 && (
      <Card variant="solid" padding="sm" className="mb-5">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-medium text-[var(--text)]">{selectedIds.size} selected</span>
          <CreditCard className="size-4 text-[var(--text-subtle)]" aria-hidden />
          <Select aria-label="Assign selected to card" value={assignCardId} onChange={(e) => setAssignCardId(e.target.value)} className="max-w-[220px]">
            <option value="">No card (unassign)</option>
            {cards.map((c) => <option key={c.id} value={String(c.id)}>{c.name}{c.last4 ? ` ····${c.last4}` : ''}</option>)}
          </Select>
          <Button
            onClick={() => bulkAssignCard.mutate({ ids: Array.from(selectedIds), cardId: assignCardId ? Number(assignCardId) : null })}
            loading={bulkAssignCard.isPending}
          >
            Assign to card
          </Button>
          <Button variant="ghost" leftIcon={<X className="size-4" />} onClick={() => setSelectedIds(new Set())}>Clear selection</Button>
        </div>
      </Card>
    )}

    {isLoading ? (
      <Skeleton className="h-64" />
    ) : transactions.length === 0 ? (
      <Empty
        title="No transactions"
        description="Import a statement or add a transaction manually."
        action={
          <div className="flex gap-2">
            <Button leftIcon={<Plus className="size-4" />} onClick={() => setShowAddModal(true)}>Add transaction</Button>
            <Button variant="secondary" leftIcon={<Upload className="size-4" />} onClick={() => setImportMode('card')}>Import statement</Button>
          </div>
        }
      />
    ) : (
      <Card variant="solid" padding="none" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-strong)] bg-[var(--surface-muted)] text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--text-subtle)]">
                <th className="px-5 py-3">
                  <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={allPageSelected} onChange={toggleSelectAll} aria-label="Select all transactions" />
                </th>
                <th className="px-5 py-3">Date</th>
                <th className="px-5 py-3">Description</th>
                <th className="px-5 py-3">Sort</th>
                {showExpensed && <th className="px-5 py-3 text-center">Expensed</th>}
                <th className="px-5 py-3">Source</th>
                <th className="px-5 py-3 text-right">Amount</th>
                <th className="px-3 py-3"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx, i) => (
                <tr key={tx.id} className={cn('border-b border-[var(--border)] transition-colors duration-150 last:border-0 hover:bg-[var(--surface-muted)]', selectedIds.has(tx.id) && 'bg-[var(--accent-soft)]', i < 16 && ROW_ANIM)} style={rowDelay(i)}>
                  <td className="px-5 py-3">
                    <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={selectedIds.has(tx.id)} onChange={() => toggleSelected(tx.id)} aria-label={`Select ${tx.description}`} />
                  </td>
                  <td className="whitespace-nowrap px-5 py-3 text-xs text-[var(--text-subtle)]">{fmtDate(tx.transaction_date)}</td>
                  <td className="px-5 py-3 font-medium">{tx.description}</td>
                  <td className="px-5 py-3">
                    {tx.classification
                      ? <Badge tone={tx.classification === 'work' ? 'accent' : 'success'}>{tx.classification === 'work' ? 'Work' : 'Personal'}</Badge>
                      : <Badge tone="muted">Unsorted</Badge>}
                  </td>
                  {showExpensed && (
                    <td className="px-5 py-3 text-center">
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--accent)]"
                        checked={tx.expensed}
                        disabled={tx.classification !== 'work' || updateExpensed.isPending}
                        onChange={(e) => updateExpensed.mutate({ id: tx.id, next: e.target.checked })}
                        aria-label={`Mark ${tx.description} as expensed`}
                      />
                    </td>
                  )}
                  <td className="whitespace-nowrap px-5 py-3 text-[var(--text-muted)]">
                    {tx.is_manual
                      ? <Badge tone="muted">Manual</Badge>
                      : (tx.statement_format ?? '-')}
                  </td>
                  <td className={cn('whitespace-nowrap px-5 py-3 text-right font-bold tabular-nums', tx.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>
                    {signedMoney(tx)}
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center justify-end gap-3">
                      <button
                        type="button"
                        aria-label={`Edit ${tx.description}`}
                        onClick={() => setEditingTx(tx)}
                        className="text-[var(--text-subtle)] hover:text-[var(--accent)] transition-colors"
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${tx.description}`}
                        onClick={() => handleDelete(tx)}
                        disabled={deleteMutation.isPending}
                        className="text-[var(--text-subtle)] hover:text-[var(--danger)] transition-colors disabled:opacity-40"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {(hasNextPage || total > transactions.length) && (
          <div className="flex items-center justify-center gap-3 border-t border-[var(--border)] px-5 py-4">
            <span className="text-xs text-[var(--text-subtle)]">Showing {transactions.length} of {total}</span>
            {hasNextPage && (
              <Button variant="secondary" onClick={() => fetchNextPage()} loading={isFetchingNextPage}>Load more</Button>
            )}
          </div>
        )}
      </Card>
    )}

    {showAddModal && <AddTransactionModal onClose={() => setShowAddModal(false)} onSuccess={() => qc.invalidateQueries({ queryKey: ['transactions'] })} />}
    {editingTx && <EditTransactionModal tx={editingTx} onClose={() => setEditingTx(null)} />}
    {importMode && <ImportModal mode={importMode} onClose={() => setImportMode(null)} />}
  </div>
}
