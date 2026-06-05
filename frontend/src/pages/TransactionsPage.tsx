import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { CreditCard, Landmark, Pencil, Plus, Trash2, Upload, X } from 'lucide-react'
import { cardsApi } from '../api/cards'
import { transactionsApi } from '../api/transactions'
import type { ClassificationFilter, ExpensedFilter, Transaction, TransactionCreatePayload, TransactionPage, TransactionType } from '../types'

const PAGE_SIZE = 200

// The transaction caches hold either a single TransactionPage (inbox queries) or
// an InfiniteData<TransactionPage> (this page's paginated list). Apply an
// update/remove to a row across whichever shape a cache entry holds; returning
// null from `fn` drops the row.
type TxCache = TransactionPage | InfiniteData<TransactionPage>

function patchPage(page: TransactionPage, fn: (tx: Transaction) => Transaction | null): TransactionPage {
  const items: Transaction[] = []
  for (const tx of page.items) {
    const next = fn(tx)
    if (next) items.push(next)
  }
  return { ...page, items }
}

function patchTxCache(current: TxCache | undefined, fn: (tx: Transaction) => Transaction | null): TxCache | undefined {
  if (!current) return current
  if ('pages' in current) {
    return { ...current, pages: current.pages.map((p) => patchPage(p, fn)) }
  }
  return patchPage(current, fn)
}
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { ImportModal } from '../components/ImportModal'
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Skeleton } from '../components/ui'
import { useConfirm } from '../components/ui/confirm-context'
import { useToast } from '../components/ui/toast-context'
import { useCategories } from '../hooks/useCategories'

function fmtDate(d: string) { return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
function signedMoney(tx: Transaction) { return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}` }

function rowDelay(i: number) {
  return i < 16 ? { animationDelay: `${Math.min(i, 12) * 25}ms` } : undefined
}
const ROW_ANIM = 'animate-[fadeInUp_360ms_var(--ease-out)_both]'

interface AddTransactionForm {
  transaction_date: string
  description: string
  amount: string
  transaction_type: TransactionType
  classification: string
  personal_category: string
  expensed: boolean
}

const EMPTY_FORM: AddTransactionForm = {
  transaction_date: new Date().toISOString().slice(0, 10),
  description: '',
  amount: '',
  transaction_type: 'debit',
  classification: '',
  personal_category: '',
  expensed: false,
}

interface AddTransactionModalProps {
  onClose: () => void
  onSuccess: () => void
}

function AddTransactionModal({ onClose, onSuccess }: AddTransactionModalProps) {
  const [form, setForm] = useState<AddTransactionForm>(EMPTY_FORM)
  const [error, setError] = useState('')
  const toast = useToast()
  const { categoriesFor } = useCategories()
  const modalCategoryOptions = categoriesFor({ transaction_type: form.transaction_type })

  const createMutation = useMutation({
    mutationFn: (payload: TransactionCreatePayload) => transactionsApi.createManual(payload),
    onSuccess: () => {
      toast.success('Transaction added')
      onSuccess()
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    const amountCents = Math.round(parseFloat(form.amount) * 100)
    if (!form.description.trim()) { setError('Description is required'); return }
    if (!form.amount || isNaN(amountCents) || amountCents <= 0) { setError('Enter a positive amount'); return }
    const payload: TransactionCreatePayload = {
      transaction_date: form.transaction_date,
      description: form.description.trim(),
      amount_cents: amountCents,
      transaction_type: form.transaction_type,
      classification: (form.classification as 'personal' | 'work') || null,
      personal_category: form.personal_category || null,
      expensed: form.expensed,
    }
    createMutation.mutate(payload)
  }

  const set = (key: keyof AddTransactionForm, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <Modal
      open
      onClose={onClose}
      title="Add transaction"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={createMutation.isPending}>Cancel</Button>
          <Button variant="primary" onClick={handleSubmit} disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Date" htmlFor="tx-date">
            <Input id="tx-date" type="date" value={form.transaction_date} onChange={(e) => set('transaction_date', e.target.value)} required />
          </Field>
          <Field label="Type" htmlFor="tx-type">
            <Select id="tx-type" value={form.transaction_type} onChange={(e) => set('transaction_type', e.target.value as TransactionType)}>
              <option value="debit">Debit (expense)</option>
              <option value="credit">Credit (income)</option>
            </Select>
          </Field>
        </div>
        <Field label="Description" htmlFor="tx-desc">
          <Input id="tx-desc" value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="e.g. Coffee shop" required />
        </Field>
        <Field label="Amount ($)" htmlFor="tx-amount">
          <Input id="tx-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => set('amount', e.target.value)} placeholder="0.00" required />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Classification" htmlFor="tx-class">
            <Select id="tx-class" value={form.classification} onChange={(e) => { set('classification', e.target.value); if (e.target.value !== 'personal') set('personal_category', ''); if (e.target.value !== 'work') set('expensed', false) }}>
              <option value="">— None —</option>
              <option value="personal">Personal</option>
              <option value="work">Work</option>
            </Select>
          </Field>
          {form.classification === 'personal' && (
            <Field label="Category" htmlFor="tx-cat">
              <Select id="tx-cat" value={form.personal_category} onChange={(e) => set('personal_category', e.target.value)}>
                <option value="">— None —</option>
                {modalCategoryOptions.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
          )}
          {form.classification === 'work' && (
            <Field label="Expensed" htmlFor="tx-expensed">
              <div className="flex items-center gap-2 pt-1">
                <input id="tx-expensed" type="checkbox" className="size-4 accent-[var(--accent)]" checked={form.expensed} onChange={(e) => set('expensed', e.target.checked)} />
                <label htmlFor="tx-expensed" className="text-sm text-[var(--text-subtle)]">Mark as expensed</label>
              </div>
            </Field>
          )}
        </div>
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      </form>
    </Modal>
  )
}

interface EditTransactionForm {
  classification: string
  personal_category: string
  expensed: boolean
  card_id: string
}

interface EditTransactionModalProps {
  tx: Transaction
  onClose: () => void
}

function EditTransactionModal({ tx, onClose }: EditTransactionModalProps) {
  const [form, setForm] = useState<EditTransactionForm>({
    classification: tx.classification ?? '',
    personal_category: tx.personal_category ?? '',
    expensed: tx.expensed,
    card_id: tx.card_id != null ? String(tx.card_id) : '',
  })
  const [error, setError] = useState('')
  const qc = useQueryClient()
  const toast = useToast()
  const { categoriesFor } = useCategories()
  const { data: cards = [] } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.list() })
  const modalCategoryOptions = categoriesFor({ transaction_type: tx.transaction_type })

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Pick<Transaction, 'classification' | 'personal_category' | 'expensed' | 'card_id'>>) =>
      transactionsApi.update(tx.id, data),
    onSuccess: (updated) => {
      qc.setQueriesData<TxCache>({ queryKey: ['transactions'] }, (current) => patchTxCache(current, (t) => (t.id === updated.id ? updated : t)))
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
      qc.invalidateQueries({ queryKey: ['income'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['statement'] })
      toast.success('Transaction updated')
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    updateMutation.mutate({
      classification: (form.classification as 'personal' | 'work') || null,
      personal_category: form.classification === 'personal' ? (form.personal_category || null) : null,
      expensed: form.classification === 'work' ? form.expensed : false,
      card_id: form.card_id ? Number(form.card_id) : null,
    })
  }

  const set = (key: keyof EditTransactionForm, value: string | boolean) =>
    setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <Modal
      open
      onClose={onClose}
      title="Edit transaction"
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={updateMutation.isPending}>Cancel</Button>
          <Button variant="primary" onClick={handleSubmit} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
          <p className="font-medium">{tx.description}</p>
          <p className="text-sm text-[var(--text-subtle)]">
            {fmtDate(tx.transaction_date)} · <span className={cn('font-bold tabular-nums', tx.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>{signedMoney(tx)}</span>
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Classification" htmlFor="edit-tx-class">
            <Select id="edit-tx-class" value={form.classification} onChange={(e) => { set('classification', e.target.value); if (e.target.value !== 'personal') set('personal_category', ''); if (e.target.value !== 'work') set('expensed', false) }}>
              <option value="">— None —</option>
              <option value="personal">Personal</option>
              <option value="work">Work</option>
            </Select>
          </Field>
          {form.classification === 'personal' && (
            <Field label="Category" htmlFor="edit-tx-cat">
              <Select id="edit-tx-cat" value={form.personal_category} onChange={(e) => set('personal_category', e.target.value)}>
                <option value="">— None —</option>
                {modalCategoryOptions.map((c) => <option key={c} value={c}>{c}</option>)}
              </Select>
            </Field>
          )}
          {form.classification === 'work' && (
            <Field label="Expensed" htmlFor="edit-tx-expensed">
              <div className="flex items-center gap-2 pt-1">
                <input id="edit-tx-expensed" type="checkbox" className="size-4 accent-[var(--accent)]" checked={form.expensed} onChange={(e) => set('expensed', e.target.checked)} />
                <label htmlFor="edit-tx-expensed" className="text-sm text-[var(--text-subtle)]">Mark as expensed</label>
              </div>
            </Field>
          )}
          {cards.length > 0 && (
            <Field label="Card" htmlFor="edit-tx-card">
              <Select id="edit-tx-card" value={form.card_id} onChange={(e) => set('card_id', e.target.value)}>
                <option value="">— None —</option>
                {cards.map((c) => <option key={c.id} value={String(c.id)}>{c.name}{c.last4 ? ` ····${c.last4}` : ''}</option>)}
              </Select>
            </Field>
          )}
        </div>
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      </form>
    </Modal>
  )
}

function readClassificationParam(value: string | null): ClassificationFilter {
  return value === 'personal' || value === 'work' || value === 'unsorted' ? value : 'all'
}
function readExpensedParam(value: string | null): ExpensedFilter {
  return value === 'expensed' || value === 'unexpensed' ? value : 'all'
}

export function TransactionsPage() {
  const [searchParams] = useSearchParams()
  const initialAction = searchParams.get('action')
  const [importMode, setImportMode] = useState<'card' | 'checking' | null>(initialAction === 'import' ? 'card' : null)
  const [showAddModal, setShowAddModal] = useState(initialAction === 'add')
  const [editingTx, setEditingTx] = useState<Transaction | null>(null)
  const [classification, setClassification] = useState<ClassificationFilter>(() => readClassificationParam(searchParams.get('classification')))
  const [expensed, setExpensed] = useState<ExpensedFilter>(() => readExpensedParam(searchParams.get('expensed')))
  const [personalCategory, setPersonalCategory] = useState(() => searchParams.get('personal_category') || 'all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
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
  const activePersonalCategory = showPersonalCategory ? personalCategory : 'all'

  const queryKey = ['transactions', classification, activeExpensed, activePersonalCategory, startDate, endDate]

  const { data, isLoading, hasNextPage, fetchNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => transactionsApi.list({ classification, expensed: activeExpensed, personal_category: activePersonalCategory !== 'all' ? activePersonalCategory : undefined, start_date: startDate, end_date: endDate, limit: PAGE_SIZE, skip: pageParam }),
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
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => transactionsApi.deleteTransaction(id),
    onSuccess: (deleted) => {
      qc.setQueriesData<TxCache>({ queryKey: ['transactions'] }, (current) => patchTxCache(current, (tx) => (tx.id === deleted.id ? null : tx)))
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['imports'] })
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
              transactionsApi.createManual(payload).then(() => qc.invalidateQueries({ queryKey: ['transactions'] }))
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

  const hasFilter = classification !== 'all' || activeExpensed !== 'all' || activePersonalCategory !== 'all' || startDate || endDate

  return <div>
    <PageHeader
      eyebrow="Ledger"
      title="Transactions"
      subtitle="Imported spending activity"
      actions={
        <div className="flex gap-2">
          <Button leftIcon={<Plus className="size-4" />} onClick={() => setShowAddModal(true)}>Add</Button>
          <Button leftIcon={<Upload className="size-4" />} onClick={() => setImportMode('card')}>Import</Button>
          <Button variant="secondary" leftIcon={<Landmark className="size-4" />} onClick={() => setImportMode('checking')}>Import Checking</Button>
        </div>
      }
    />
    <Card variant="solid" padding="sm" className="mb-5">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto_auto] sm:items-end">
        <Field label="Type" htmlFor="class">
          <Select id="class" value={classification} onChange={(e) => { const next = e.target.value as ClassificationFilter; setClassification(next); if (next !== 'work') setExpensed('all'); if (next !== 'personal') setPersonalCategory('all') }}>
            <option value="all">All</option>
            <option value="unsorted">Unsorted</option>
            <option value="personal">Personal</option>
            <option value="work">Work</option>
          </Select>
        </Field>
        {showExpensed && <Field label="Expensed" htmlFor="expensed"><Select id="expensed" value={expensed} onChange={(e) => setExpensed(e.target.value as ExpensedFilter)}><option value="all">All work</option><option value="unexpensed">Needs expensing</option><option value="expensed">Expensed</option></Select></Field>}
        {showPersonalCategory && <Field label="Category" htmlFor="personal-cat"><Select id="personal-cat" value={personalCategory} onChange={(e) => setPersonalCategory(e.target.value)}><option value="all">All categories</option><option value="uncategorized">Uncategorized</option>{allCategories.map((c) => <option key={c} value={c}>{c}</option>)}</Select></Field>}
        <Field label="From" htmlFor="from"><Input id="from" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></Field>
        <Field label="To" htmlFor="to"><Input id="to" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></Field>
        {hasFilter && <Button variant="ghost" leftIcon={<X className="size-4" />} onClick={() => { setClassification('all'); setExpensed('all'); setPersonalCategory('all'); setStartDate(''); setEndDate('') }}>Clear</Button>}
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
