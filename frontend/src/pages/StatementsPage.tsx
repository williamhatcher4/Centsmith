import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard, Pencil, Plus, Trash2 } from 'lucide-react'
import { cardsApi } from '../api/cards'
import { transactionsApi } from '../api/transactions'
import type { Card as CardType, CardPayload } from '../types'
import { formatMoney, parseMoneyToCents } from '../utils/money'
import { generateStatementCycles } from '../utils/statementCycles'
import {
  Badge,
  Button,
  Card,
  CardHeader,
  Empty,
  Field,
  IconButton,
  Input,
  Modal,
  PageHeader,
  Select,
  Skeleton,
  StatCard,
} from '../components/ui'
import { useToast } from '../components/ui/toast-context'
import { useConfirm } from '../components/ui/confirm-context'

const money = (n: number) => formatMoney(Math.round(n))

function fmtDate(iso: string) {
  const [y, m, d] = iso.split('-')
  return `${d}/${m}/${y}`
}

interface CardFormState {
  name: string
  last4: string
  statement_day: string
}

function emptyForm(): CardFormState {
  return { name: '', last4: '', statement_day: '' }
}

function CardFormModal({
  card,
  onClose,
}: {
  card: CardType | null // null => create
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<CardFormState>(
    card
      ? {
          name: card.name,
          last4: card.last4 ?? '',
          statement_day: card.statement_day != null ? String(card.statement_day) : '',
        }
      : emptyForm(),
  )
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: (payload: CardPayload) =>
      card ? cardsApi.update(card.id, payload) : cardsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cards'] })
      qc.invalidateQueries({ queryKey: ['statement'] })
      toast.success(card ? 'Card updated' : 'Card added')
      onClose()
    },
    onError: (err: Error) => setError(err.message),
  })

  function submit() {
    setError('')
    const name = form.name.trim()
    if (!name) {
      setError('Card name is required')
      return
    }
    const last4 = form.last4.trim()
    if (last4 && !/^\d{1,4}$/.test(last4)) {
      setError('Last 4 must be up to 4 digits')
      return
    }
    let statement_day: number | null = null
    if (form.statement_day.trim()) {
      const day = Number(form.statement_day)
      if (!Number.isInteger(day) || day < 1 || day > 31) {
        setError('Statement day must be between 1 and 31')
        return
      }
      statement_day = day
    }
    mutation.mutate({ name, last4: last4 || null, statement_day })
  }

  const set = (key: keyof CardFormState, value: string) => setForm((prev) => ({ ...prev, [key]: value }))

  return (
    <Modal
      open
      onClose={onClose}
      title={card ? 'Edit card' : 'Add card'}
      size="md"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-1">
        <Field label="Card name" htmlFor="card-name">
          <Input
            id="card-name"
            autoFocus
            value={form.name}
            placeholder="e.g. Amex Platinum"
            onChange={(e) => set('name', e.target.value)}
          />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Last 4 (optional)" htmlFor="card-last4">
            <Input
              id="card-last4"
              inputMode="numeric"
              value={form.last4}
              placeholder="1009"
              maxLength={4}
              onChange={(e) => set('last4', e.target.value.replace(/\D/g, ''))}
            />
          </Field>
          <Field label="Statement closing day" htmlFor="card-day" hint="1–31">
            <Input
              id="card-day"
              inputMode="numeric"
              value={form.statement_day}
              placeholder="21"
              onChange={(e) => set('statement_day', e.target.value.replace(/\D/g, ''))}
            />
          </Field>
        </div>
        {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      </div>
    </Modal>
  )
}

function StatementView({ card }: { card: CardType }) {
  const cycles = useMemo(
    () => (card.statement_day ? generateStatementCycles(card.statement_day) : []),
    [card.statement_day],
  )
  const [mode, setMode] = useState<'cycle' | 'custom'>(cycles.length ? 'cycle' : 'custom')
  const [cycleIndex, setCycleIndex] = useState(0)
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [bankFigure, setBankFigure] = useState('')

  const window =
    mode === 'cycle' && cycles[cycleIndex]
      ? { start_date: cycles[cycleIndex].start, end_date: cycles[cycleIndex].end }
      : customStart && customEnd
        ? { start_date: customStart, end_date: customEnd }
        : null

  const { data: statement, isLoading } = useQuery({
    queryKey: ['statement', card.id, window?.start_date, window?.end_date],
    queryFn: () => cardsApi.statement(card.id, window!),
    enabled: !!window,
  })

  const { data: txPage } = useQuery({
    queryKey: ['transactions', 'statement', card.id, window?.start_date, window?.end_date],
    queryFn: () =>
      transactionsApi.list({
        card_id: card.id,
        start_date: window!.start_date,
        end_date: window!.end_date,
        limit: 500,
      }),
    enabled: !!window,
  })
  const rows = txPage?.items ?? []

  const bankCents = bankFigure.trim() ? parseMoneyToCents(bankFigure) : null
  const diff = bankCents != null && statement ? bankCents - statement.net_cents : null

  return (
    <div className="flex flex-col gap-6">
      <Card variant="solid" padding="md">
        <CardHeader title="Statement window" subtitle={`${card.name}${card.last4 ? ` ····${card.last4}` : ''}`} />
        <div className="flex flex-col gap-4">
          {cycles.length > 0 && (
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Billing cycle" htmlFor="cycle-select" className="mb-0 min-w-[220px] flex-1">
                <Select
                  id="cycle-select"
                  value={mode === 'cycle' ? String(cycleIndex) : 'custom'}
                  onChange={(e) => {
                    if (e.target.value === 'custom') {
                      setMode('custom')
                    } else {
                      setMode('cycle')
                      setCycleIndex(Number(e.target.value))
                    }
                  }}
                >
                  {cycles.map((c, i) => (
                    <option key={c.end} value={String(i)}>
                      {c.label}
                      {i === 0 ? ' (current)' : ''}
                    </option>
                  ))}
                  <option value="custom">Custom date range…</option>
                </Select>
              </Field>
            </div>
          )}
          {(mode === 'custom' || cycles.length === 0) && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Start date" htmlFor="custom-start" className="mb-0">
                <Input id="custom-start" type="date" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
              </Field>
              <Field label="End date" htmlFor="custom-end" className="mb-0">
                <Input id="custom-end" type="date" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
              </Field>
            </div>
          )}
          {!card.statement_day && cycles.length === 0 && (
            <p className="text-xs text-[var(--text-subtle)]">
              Set a statement closing day on this card to get automatic billing cycles.
            </p>
          )}
        </div>
      </Card>

      {!window ? (
        <Empty title="Pick a date range" description="Choose a billing cycle or enter a custom start and end date." />
      ) : isLoading || !statement ? (
        <Skeleton className="h-32" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Charges" value={formatMoney(statement.charges_cents)} animateTo={statement.charges_cents} format={money} tone="negative" hint={`${statement.charge_count} charge${statement.charge_count === 1 ? '' : 's'}`} />
            <StatCard label="Payments / credits" value={formatMoney(statement.payments_cents)} animateTo={statement.payments_cents} format={money} tone="positive" hint={`${statement.payment_count} item${statement.payment_count === 1 ? '' : 's'}`} />
            <StatCard label="Net this statement" value={formatMoney(statement.net_cents)} animateTo={statement.net_cents} format={money} gradient hint="Charges − payments" />
          </div>

          <Card variant="solid" padding="md">
            <CardHeader title="Reconcile" subtitle="Enter the balance/total from your bank statement to confirm it matches." />
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Bank statement figure" htmlFor="bank-figure" className="mb-0 min-w-[200px] flex-1">
                <Input
                  id="bank-figure"
                  inputMode="decimal"
                  placeholder="$0.00"
                  value={bankFigure}
                  onChange={(e) => setBankFigure(e.target.value)}
                />
              </Field>
              {diff != null && (
                <div className="pb-1">
                  {diff === 0 ? (
                    <Badge tone="success" size="md" dot>
                      Matches net ({formatMoney(statement.net_cents)})
                    </Badge>
                  ) : (
                    <Badge tone="danger" size="md" dot>
                      Off by {formatMoney(Math.abs(diff))} ({diff > 0 ? 'bank higher' : 'app higher'})
                    </Badge>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card padding="md">
            <CardHeader title="Transactions in window" subtitle={`${rows.length} row${rows.length === 1 ? '' : 's'}`} />
            {rows.length === 0 ? (
              <p className="text-sm text-[var(--text-subtle)]">No transactions on this card in the selected window.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[var(--text-subtle)]">
                      <th className="py-2 pr-3 font-medium">Date</th>
                      <th className="py-2 pr-3 font-medium">Description</th>
                      <th className="py-2 pl-3 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((tx) => (
                      <tr key={tx.id} className="border-t border-[var(--border)]">
                        <td className="py-2 pr-3 tabular-nums text-[var(--text-subtle)]">{fmtDate(tx.transaction_date)}</td>
                        <td className="py-2 pr-3">{tx.description}</td>
                        <td
                          className={
                            'py-2 pl-3 text-right font-semibold tabular-nums ' +
                            (tx.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--text)]')
                          }
                        >
                          {tx.transaction_type === 'credit' ? '−' : ''}
                          {formatMoney(tx.amount_cents)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  )
}

export function StatementsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { data: cards, isLoading } = useQuery({ queryKey: ['cards'], queryFn: () => cardsApi.list() })
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [formCard, setFormCard] = useState<CardType | null>(null)
  const [formOpen, setFormOpen] = useState(false)

  const deleteMutation = useMutation({
    mutationFn: (id: number) => cardsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cards'] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      toast.success('Card deleted')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const cardList = cards ?? []
  const selected = cardList.find((c) => c.id === selectedId) ?? cardList[0] ?? null

  async function handleDelete(card: CardType) {
    const ok = await confirm({
      title: `Delete "${card.name}"?`,
      message: 'Transactions on this card are kept but will no longer be linked to it.',
      confirmLabel: 'Delete',
      destructive: true,
    })
    if (ok) {
      if (selectedId === card.id) setSelectedId(null)
      deleteMutation.mutate(card.id)
    }
  }

  function openCreate() {
    setFormCard(null)
    setFormOpen(true)
  }

  function openEdit(card: CardType) {
    setFormCard(card)
    setFormOpen(true)
  }

  if (isLoading) return <Skeleton className="h-64" />

  return (
    <div>
      <PageHeader
        eyebrow="Reconcile"
        title="Statements"
        subtitle="Match each card's totals against your bank statement"
        actions={
          <Button leftIcon={<Plus className="size-4" />} onClick={openCreate}>
            Add card
          </Button>
        }
      />

      {cardList.length === 0 ? (
        <Empty
          icon={<CreditCard className="size-6" />}
          title="No cards yet"
          description="Add a credit card to start reconciling its statements. Set the closing day to get automatic billing cycles."
          action={
            <Button leftIcon={<Plus className="size-4" />} onClick={openCreate}>
              Add card
            </Button>
          }
        />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <div className="flex flex-col gap-3">
            {cardList.map((card) => {
              const active = selected?.id === card.id
              return (
                <div
                  key={card.id}
                  className={
                    'rounded-[var(--radius-lg)] border px-4 py-3 transition-colors ' +
                    (active
                      ? 'border-[var(--accent)] bg-[var(--accent-soft)]'
                      : 'border-[var(--border)] bg-[var(--surface)] hover:border-[var(--border-strong)]')
                  }
                >
                  <button type="button" className="block w-full text-left" onClick={() => setSelectedId(card.id)}>
                    <div className="flex items-center gap-2">
                      <CreditCard className="size-4 text-[var(--text-subtle)]" aria-hidden />
                      <span className="font-medium text-[var(--text)]">{card.name}</span>
                    </div>
                    <div className="mt-1 text-xs text-[var(--text-subtle)]">
                      {card.last4 ? `····${card.last4}` : 'No card number'}
                      {card.statement_day ? ` · closes on the ${card.statement_day}` : ' · no closing day'}
                    </div>
                  </button>
                  <div className="mt-2 flex justify-end gap-1">
                    <IconButton aria-label={`Edit ${card.name}`} icon={<Pencil className="size-4" />} size="sm" onClick={() => openEdit(card)} />
                    <IconButton aria-label={`Delete ${card.name}`} icon={<Trash2 className="size-4" />} size="sm" variant="danger" onClick={() => handleDelete(card)} />
                  </div>
                </div>
              )
            })}
          </div>

          {selected ? <StatementView key={selected.id} card={selected} /> : null}
        </div>
      )}

      {formOpen && <CardFormModal card={formCard} onClose={() => setFormOpen(false)} />}
    </div>
  )
}
