import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowRight, BriefcaseBusiness, Inbox, Receipt, Store, TrendingDown, TrendingUp, WalletCards, Wallet } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import { formatMoney } from '../utils/money'
import { cn } from '../utils/cn'
import { Card, CardHeader, PageHeader, SegmentedControl, Skeleton, StatCard } from '../components/ui'
import { useReducedMotion } from '../hooks/useReducedMotion'

const money = (n: number) => formatMoney(Math.round(n))
const signedMoney = (n: number) => `${n < 0 ? '-' : ''}${formatMoney(Math.round(Math.abs(n)))}`

const MERCHANT_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)']

function MoMHint({ pct }: { pct: number | null }) {
  if (pct === null) return <span className="text-[var(--text-subtle)]">No prior month</span>
  if (Math.abs(pct) < 0.5) return <span className="text-[var(--text-subtle)]">About flat vs last month</span>
  const up = pct > 0
  return (
    <span className={cn('inline-flex items-center gap-1 font-semibold', up ? 'text-[var(--danger)]' : 'text-[var(--success)]')}>
      {up ? <TrendingUp className="size-3.5" /> : <TrendingDown className="size-3.5" />}
      {Math.abs(pct).toFixed(0)}% {up ? 'more' : 'less'} vs last month
    </span>
  )
}

export function DashboardPage() {
  const reduced = useReducedMotion()
  const [months, setMonths] = useState(12)
  const { data, isLoading } = useQuery({ queryKey: ['dashboard', months], queryFn: () => transactionsApi.dashboard(months) })
  const chartData =
    data?.months.map((m) => ({
      month: m.month,
      Personal: m.personal_cents / 100,
      Work: m.work_cents / 100,
      Income: (m.income_cents + m.reimbursement_cents) / 100,
    })) ?? []

  const incomeCents = data ? data.income_total_cents + data.reimbursement_total_cents : 0
  const inboxCount = data ? data.unsorted_count + data.uncategorized_income_count : 0
  const netCents = data ? incomeCents - data.personal_total_cents : 0
  const savingsRate = incomeCents > 0 ? (netCents / incomeCents) * 100 : null
  const owedCents = data?.unexpensed_work_cents ?? 0
  const owedCount = data?.unexpensed_work_count ?? 0
  const topMerchants = data?.top_merchants ?? []

  const monthsArr = data?.months ?? []
  const lastPersonal = monthsArr.length ? monthsArr[monthsArr.length - 1].personal_cents : 0
  const prevPersonal = monthsArr.length > 1 ? monthsArr[monthsArr.length - 2].personal_cents : null
  const momPct = prevPersonal && prevPersonal > 0 ? ((lastPersonal - prevPersonal) / prevPersonal) * 100 : null

  const cards: ReactNode[] = data
    ? [
        <StatCard
          key="personal"
          label="Personal spending"
          value={money(data.personal_total_cents)}
          animateTo={data.personal_total_cents}
          format={money}
          icon={<WalletCards className="size-4" />}
          gradient
          hint={<MoMHint pct={momPct} />}
        />,
        <StatCard
          key="work"
          label="Work spending"
          value={money(data.work_total_cents)}
          animateTo={data.work_total_cents}
          format={money}
          icon={<BriefcaseBusiness className="size-4" />}
          tone="accent"
        />,
        <StatCard
          key="income"
          label="Income"
          value={money(incomeCents)}
          animateTo={incomeCents}
          format={money}
          icon={<TrendingUp className="size-4" />}
          tone="positive"
        />,
        <StatCard
          key="net"
          label="Net cash flow"
          value={signedMoney(netCents)}
          animateTo={netCents}
          format={signedMoney}
          icon={<Wallet className="size-4" />}
          tone={netCents >= 0 ? 'positive' : 'negative'}
          hint={
            savingsRate === null
              ? 'Add income to see savings rate'
              : netCents >= 0
                ? `Saving ${savingsRate.toFixed(0)}% of income`
                : 'Spending exceeds income'
          }
        />,
        <Link
          key="owed"
          to="/transactions?classification=work&expensed=unexpensed"
          className="block rounded-[var(--radius-lg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-ring)]"
          aria-label={`Awaiting reimbursement: ${owedCount} work transactions`}
        >
          <StatCard
            label="Awaiting reimbursement"
            value={money(owedCents)}
            animateTo={owedCents}
            format={money}
            icon={<Receipt className="size-4" />}
            tone={owedCents > 0 ? 'accent' : 'neutral'}
            hint={
              <span className="inline-flex items-center gap-1">
                {owedCount === 0 ? 'All caught up' : `${owedCount} item${owedCount === 1 ? '' : 's'} to expense`}
                <ArrowRight className="size-3" />
              </span>
            }
          />
        </Link>,
        <StatCard
          key="inbox"
          label="Inbox items"
          value={String(inboxCount)}
          animateTo={inboxCount}
          format={(n) => String(Math.round(n))}
          icon={<Inbox className="size-4" />}
          tone={inboxCount ? 'negative' : 'neutral'}
          hint={inboxCount ? 'Need sorting' : 'Inbox clear'}
        />,
      ]
    : []

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        subtitle="Monthly credit card spending split between Personal and Work, plus checking income"
        actions={
          <SegmentedControl
            aria-label="Dashboard range"
            value={months}
            onChange={setMonths}
            options={[{ label: '6m', value: 6 }, { label: '12m', value: 12 }, { label: '24m', value: 24 }]}
          />
        }
      />
      {isLoading || !data ? (
        <Skeleton className="h-80" />
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map((card, i) => (
              <div key={i} className="animate-[fadeInUp_400ms_var(--ease-out)_both]" style={{ animationDelay: `${i * 60}ms` }}>
                {card}
              </div>
            ))}
          </div>
          <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
            <Card padding="md">
              <CardHeader
                title="Personal, Work, and Income by month"
                subtitle={data.latest_month ? `Latest month: ${data.latest_month}` : 'No classified activity yet'}
              />
              <div className="h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="barPersonal" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--chart-3)" stopOpacity={0.95} />
                        <stop offset="100%" stopColor="var(--chart-3)" stopOpacity={0.5} />
                      </linearGradient>
                      <linearGradient id="barWork" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--chart-2)" stopOpacity={0.95} />
                        <stop offset="100%" stopColor="var(--chart-2)" stopOpacity={0.5} />
                      </linearGradient>
                      <linearGradient id="barIncome" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--success)" stopOpacity={0.95} />
                        <stop offset="100%" stopColor="var(--success)" stopOpacity={0.5} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                    <XAxis dataKey="month" tick={{ fill: 'var(--text-subtle)', fontSize: 12 }} />
                    <YAxis tick={{ fill: 'var(--text-subtle)', fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
                    <Tooltip
                      formatter={(v) => formatMoney(Math.round(Number(v) * 100))}
                      contentStyle={{
                        background: 'var(--surface-strong)',
                        border: '1px solid var(--border-strong)',
                        borderRadius: 12,
                        backdropFilter: 'var(--blur-glass)',
                        boxShadow: 'var(--shadow-md)',
                      }}
                      cursor={{ fill: 'var(--accent-soft)' }}
                    />
                    <Bar dataKey="Personal" fill="url(#barPersonal)" radius={[5, 5, 0, 0]} isAnimationActive={!reduced} animationDuration={700} />
                    <Bar dataKey="Work" fill="url(#barWork)" radius={[5, 5, 0, 0]} isAnimationActive={!reduced} animationDuration={700} />
                    <Bar dataKey="Income" fill="url(#barIncome)" radius={[5, 5, 0, 0]} isAnimationActive={!reduced} animationDuration={700} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card variant="solid" padding="md">
              <CardHeader title="Top merchants" subtitle="Where personal money went" />
              {topMerchants.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <Store className="size-6 text-[var(--text-faint)]" />
                  <p className="text-sm text-[var(--text-subtle)]">No personal spending in this range yet.</p>
                </div>
              ) : (
                <div className="flex flex-col gap-4">
                  {topMerchants.map((m, i) => {
                    const pct = data.personal_total_cents > 0 ? (m.amount_cents / data.personal_total_cents) * 100 : 0
                    const color = MERCHANT_COLORS[i % MERCHANT_COLORS.length]
                    return (
                      <div key={m.name}>
                        <div className="mb-1.5 flex items-baseline justify-between gap-3">
                          <div className="flex min-w-0 items-center gap-2">
                            <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full" style={{ background: color }} />
                            <span className="truncate text-sm font-medium text-[var(--text)]">{m.name}</span>
                            <span className="shrink-0 text-[11px] text-[var(--text-faint)]">{m.count}×</span>
                          </div>
                          <div className="shrink-0 text-sm font-semibold tabular-nums text-[var(--text)]">{formatMoney(m.amount_cents)}</div>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-muted)]">
                          <div
                            className="h-full rounded-full transition-[width] duration-500 ease-[var(--ease-out)]"
                            style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: color }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
