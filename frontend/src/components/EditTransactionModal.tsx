import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cardsApi } from '../api/cards'
import { transactionsApi } from '../api/transactions'
import type { Transaction, TransactionType } from '../types'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { patchTxCache, type TxCache } from '../utils/txCache'
import { invalidateAnalytics, invalidateLedger } from '../utils/queryInvalidation'
import { Button, Field, Input, Modal, Select } from './ui'
import { useToast } from './ui/toast-context'
import { useCategories } from '../hooks/useCategories'

function fmtDate(d: string) { return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
function signedMoney(tx: Transaction) { return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}` }

interface EditTransactionForm {
  classification: string
  personal_category: string
  expensed: boolean
  card_id: string
  amount: string
  transaction_type: TransactionType
}

interface EditTransactionModalProps {
  tx: Transaction
  onClose: () => void
}

export function EditTransactionModal({ tx, onClose }: EditTransactionModalProps) {
  const [form, setForm] = useState<EditTransactionForm>({
    classification: tx.classification ?? '',
    personal_category: tx.personal_category ?? '',
    expensed: tx.expensed,
    card_id: tx.card_id != null ? String(tx.card_id) : '',
    amount: (tx.amount_cents / 100).toFixed(2),
    transaction_type: tx.transaction_type,
  })
  const [error, setError] = useState('')
  const qc = useQueryClient()
  const toast = useToast()
  const { categoriesFor } = useCategories()
  const { data: cards = [] } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.list() })
  const modalCategoryOptions = categoriesFor({ transaction_type: form.transaction_type })

  const updateMutation = useMutation({
    mutationFn: (data: Partial<Pick<Transaction, 'classification' | 'personal_category' | 'expensed' | 'card_id' | 'amount_cents' | 'transaction_type'>>) =>
      transactionsApi.update(tx.id, data),
    onSuccess: (updated) => {
      qc.setQueriesData<TxCache>({ queryKey: ['transactions'] }, (current) => patchTxCache(current, (t) => (t.id === updated.id ? updated : t)))
      invalidateLedger(qc)
      invalidateAnalytics(qc)
      toast.success('Transaction updated')
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    const payload: Partial<Pick<Transaction, 'classification' | 'personal_category' | 'expensed' | 'card_id' | 'amount_cents' | 'transaction_type'>> = {
      classification: (form.classification as 'personal' | 'work') || null,
      personal_category: form.classification === 'personal' ? (form.personal_category || null) : null,
      expensed: form.classification === 'work' ? form.expensed : false,
      card_id: form.card_id ? Number(form.card_id) : null,
    }
    // Amount/type are editable only on manual rows; imported rows stay immutable.
    if (tx.is_manual) {
      const amountCents = Math.round(parseFloat(form.amount) * 100)
      if (!form.amount || isNaN(amountCents) || amountCents <= 0) { setError('Enter a positive amount'); return }
      payload.amount_cents = amountCents
      payload.transaction_type = form.transaction_type
    }
    updateMutation.mutate(payload)
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
        {tx.is_manual && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Amount ($)" htmlFor="edit-tx-amount">
              <Input id="edit-tx-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => set('amount', e.target.value)} placeholder="0.00" required />
            </Field>
            <Field label="Type" htmlFor="edit-tx-type">
              <Select id="edit-tx-type" value={form.transaction_type} onChange={(e) => set('transaction_type', e.target.value as TransactionType)}>
                <option value="debit">Debit (expense)</option>
                <option value="credit">Credit (income)</option>
              </Select>
            </Field>
          </div>
        )}
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
