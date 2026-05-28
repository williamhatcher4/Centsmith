import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, Plus, Trash2, Upload, X } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import type { ClassificationFilter, ExpensedFilter, Transaction, TransactionCreatePayload, TransactionType } from '../types'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { ImportModal } from '../components/ImportModal'
import { Badge, Button, Card, Empty, Field, Input, Modal, PageHeader, Select, Skeleton } from '../components/ui'
import { useConfirm } from '../components/ui/ConfirmDialog'
import { useToast } from '../components/ui/Toaster'
import { useCategories } from '../hooks/useCategories'

function fmtDate(d: string) { return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
function signedMoney(tx: Transaction) { return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}` }

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

export function TransactionsPage() {
  const [importMode, setImportMode] = useState<'card' | 'checking' | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [classification, setClassification] = useState<ClassificationFilter>('all')
  const [expensed, setExpensed] = useState<ExpensedFilter>('all')
  const [personalCategory, setPersonalCategory] = useState('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const qc = useQueryClient()
  const confirm = useConfirm()
  const toast = useToast()
  const { all: allCategories } = useCategories()
  const showExpensed = classification === 'work'
  const activeExpensed = showExpensed ? expensed : 'all'
  const showPersonalCategory = classification === 'personal'
  const activePersonalCategory = showPersonalCategory ? personalCategory : 'all'

  const queryKey = ['transactions', classification, activeExpensed, activePersonalCategory, startDate, endDate]

  const { data: transactions = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => transactionsApi.list({ classification, expensed: activeExpensed, personal_category: activePersonalCategory !== 'all' ? activePersonalCategory : undefined, start_date: startDate, end_date: endDate, limit: 1000 }),
  })

  const updateExpensed = useMutation({
    mutationFn: ({ id, next }: { id: number; next: boolean }) => transactionsApi.update(id, { expensed: next }),
    onSuccess: (updated) => {
      qc.setQueriesData<Transaction[]>({ queryKey: ['transactions'] }, (current) => current?.map((tx) => (tx.id === updated.id ? updated : tx)))
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => transactionsApi.deleteTransaction(id),
    onSuccess: (deleted) => {
      qc.setQueriesData<Transaction[]>({ queryKey: ['transactions'] }, (current) => current?.filter((tx) => tx.id !== deleted.id))
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

  async function handleDelete(tx: Transaction) {
    const ok = await confirm({
      title: 'Delete transaction',
      message: `Delete "${tx.description}"? This cannot be undone from this dialog${tx.is_manual ? ' — but you can Undo via the notification' : ''}.`,
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (ok) deleteMutation.mutate(tx.id)
  }

  const hasFilter = classification !== 'all' || activeExpensed !== 'all' || activePersonalCategory !== 'all' || startDate || endDate

  return <div>
    <PageHeader
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
              <tr className="border-b border-[var(--border)] text-left text-xs font-semibold uppercase text-[var(--text-subtle)]">
                <th className="px-5 py-3">Date</th>
                <th className="px-5 py-3">Description</th>
                <th className="px-5 py-3">Sort</th>
                {showExpensed && <th className="px-5 py-3 text-center">Expensed</th>}
                <th className="px-5 py-3">Source</th>
                <th className="px-5 py-3 text-right">Amount</th>
                <th className="px-3 py-3" />
              </tr>
            </thead>
            <tbody>
              {transactions.map((tx) => (
                <tr key={tx.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-muted)]">
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
                    <button
                      aria-label={`Delete ${tx.description}`}
                      onClick={() => handleDelete(tx)}
                      disabled={deleteMutation.isPending}
                      className="text-[var(--text-subtle)] hover:text-[var(--danger)] transition-colors disabled:opacity-40"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    )}

    {showAddModal && <AddTransactionModal onClose={() => setShowAddModal(false)} onSuccess={() => qc.invalidateQueries({ queryKey: ['transactions'] })} />}
    {importMode && <ImportModal mode={importMode} onClose={() => setImportMode(null)} />}
  </div>
}
