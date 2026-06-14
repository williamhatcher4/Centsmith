import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { transactionsApi } from '../api/transactions'
import type { TransactionCreatePayload, TransactionType } from '../types'
import { invalidateAnalytics, invalidateLedger } from '../utils/queryInvalidation'
import { Button, Field, Input, Modal, Select } from './ui'
import { useToast } from './ui/toast-context'
import { useCategories } from '../hooks/useCategories'

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

export function AddTransactionModal({ onClose, onSuccess }: AddTransactionModalProps) {
  const [form, setForm] = useState<AddTransactionForm>(EMPTY_FORM)
  const [error, setError] = useState('')
  const qc = useQueryClient()
  const toast = useToast()
  const { categoriesFor } = useCategories()
  const modalCategoryOptions = categoriesFor({ transaction_type: form.transaction_type })

  const createMutation = useMutation({
    mutationFn: (payload: TransactionCreatePayload) => transactionsApi.createManual(payload),
    onSuccess: () => {
      invalidateLedger(qc)
      invalidateAnalytics(qc)
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
