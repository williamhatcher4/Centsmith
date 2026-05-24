import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, Upload, X } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import type { ClassificationFilter, ExpensedFilter, Transaction } from '../types'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { ImportModal } from '../components/ImportModal'
import { Badge, Button, Card, Empty, Field, Input, PageHeader, Select, Skeleton } from '../components/ui'

function fmtDate(d: string) { return new Date(`${d}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) }
function signedMoney(tx: Transaction) { return `${tx.transaction_type === 'credit' ? '+' : '-'}${formatMoney(tx.amount_cents)}` }

export function TransactionsPage() {
  const [importMode, setImportMode] = useState<'card' | 'checking' | null>(null)
  const [classification, setClassification] = useState<ClassificationFilter>('all')
  const [expensed, setExpensed] = useState<ExpensedFilter>('all')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const qc = useQueryClient()
  const showExpensed = classification === 'work'
  const activeExpensed = showExpensed ? expensed : 'all'

  const { data: transactions = [], isLoading } = useQuery({
    queryKey: ['transactions', classification, activeExpensed, startDate, endDate],
    queryFn: () => transactionsApi.list({ classification, expensed: activeExpensed, start_date: startDate, end_date: endDate, limit: 1000 }),
  })
  const updateExpensed = useMutation({
    mutationFn: ({ id, next }: { id: number; next: boolean }) => transactionsApi.update(id, { expensed: next }),
    onSuccess: (updated) => {
      qc.setQueriesData<Transaction[]>({ queryKey: ['transactions'] }, (current) => current?.map((tx) => (tx.id === updated.id ? updated : tx)))
      qc.invalidateQueries({ queryKey: ['transactions'] })
    },
  })
  const hasFilter = classification !== 'all' || activeExpensed !== 'all' || startDate || endDate

  return <div>
    <PageHeader title="Transactions" subtitle="Imported spending activity" actions={<div className="flex gap-2"><Button leftIcon={<Upload className="size-4" />} onClick={() => setImportMode('card')}>Import</Button><Button variant="secondary" leftIcon={<Landmark className="size-4" />} onClick={() => setImportMode('checking')}>Import Checking</Button></div>} />
    <Card variant="solid" padding="sm" className="mb-5"><div className="grid gap-3 sm:grid-cols-[1fr_auto_auto_auto_auto] sm:items-end">
      <Field label="Type" htmlFor="class"><Select id="class" value={classification} onChange={(e) => { const next = e.target.value as ClassificationFilter; setClassification(next); if (next !== 'work') setExpensed('all') }}><option value="all">All</option><option value="unsorted">Unsorted</option><option value="personal">Personal</option><option value="work">Work</option></Select></Field>
      {showExpensed && <Field label="Expensed" htmlFor="expensed"><Select id="expensed" value={expensed} onChange={(e) => setExpensed(e.target.value as ExpensedFilter)}><option value="all">All work</option><option value="unexpensed">Needs expensing</option><option value="expensed">Expensed</option></Select></Field>}
      <Field label="From" htmlFor="from"><Input id="from" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} /></Field>
      <Field label="To" htmlFor="to"><Input id="to" type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} /></Field>
      {hasFilter && <Button variant="ghost" leftIcon={<X className="size-4" />} onClick={() => { setClassification('all'); setExpensed('all'); setStartDate(''); setEndDate('') }}>Clear</Button>}
    </div></Card>
    {isLoading ? <Skeleton className="h-64" /> : transactions.length === 0 ? <Empty title="No transactions" description="Import a statement to get started." action={<Button leftIcon={<Upload className="size-4" />} onClick={() => setImportMode('card')}>Import statement</Button>} /> : <Card variant="solid" padding="none" className="overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b border-[var(--border)] text-left text-xs font-semibold uppercase text-[var(--text-subtle)]"><th className="px-5 py-3">Date</th><th className="px-5 py-3">Description</th><th className="px-5 py-3">Sort</th>{showExpensed && <th className="px-5 py-3 text-center">Expensed</th>}<th className="px-5 py-3">Format</th><th className="px-5 py-3 text-right">Amount</th></tr></thead><tbody>{transactions.map((tx) => <tr key={tx.id} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface-muted)]"><td className="whitespace-nowrap px-5 py-3 text-xs text-[var(--text-subtle)]">{fmtDate(tx.transaction_date)}</td><td className="px-5 py-3 font-medium">{tx.description}</td><td className="px-5 py-3">{tx.classification ? <Badge tone={tx.classification === 'work' ? 'accent' : 'success'}>{tx.classification === 'work' ? 'Work' : 'Personal'}</Badge> : <Badge tone="muted">Unsorted</Badge>}</td>{showExpensed && <td className="px-5 py-3 text-center"><input type="checkbox" className="size-4 accent-[var(--accent)]" checked={tx.expensed} disabled={tx.classification !== 'work' || updateExpensed.isPending} onChange={(e) => updateExpensed.mutate({ id: tx.id, next: e.target.checked })} aria-label={`Mark ${tx.description} as expensed`} /></td>}<td className="whitespace-nowrap px-5 py-3 text-[var(--text-muted)]">{tx.statement_format ?? '-'}</td><td className={cn('whitespace-nowrap px-5 py-3 text-right font-bold tabular-nums', tx.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>{signedMoney(tx)}</td></tr>)}</tbody></table></div></Card>}
    {importMode && <ImportModal mode={importMode} onClose={() => setImportMode(null)} />}
  </div>
}
