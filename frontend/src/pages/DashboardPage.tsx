import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Inbox, BriefcaseBusiness, TrendingUp, WalletCards } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import { formatMoney } from '../utils/money'
import { Card, CardHeader, PageHeader, Skeleton, StatCard } from '../components/ui'
import { useReducedMotion } from '../hooks/useReducedMotion'

const money = (n: number) => formatMoney(Math.round(n))

export function DashboardPage() {
  const reduced = useReducedMotion()
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: transactionsApi.dashboard })
  const chartData =
    data?.months.map((m) => ({
      month: m.month,
      Personal: m.personal_cents / 100,
      Work: m.work_cents / 100,
      Income: (m.income_cents + m.reimbursement_cents) / 100,
    })) ?? []

  const incomeCents = data ? data.income_total_cents + data.reimbursement_total_cents : 0
  const inboxCount = data ? data.unsorted_count + data.uncategorized_income_count : 0

  const stats = data
    ? [
        {
          label: 'Personal spending',
          value: data.personal_total_cents,
          fmt: money,
          icon: <WalletCards className="size-4" />,
          tone: 'neutral' as const,
          gradient: true,
        },
        {
          label: 'Work spending',
          value: data.work_total_cents,
          fmt: money,
          icon: <BriefcaseBusiness className="size-4" />,
          tone: 'accent' as const,
        },
        {
          label: 'Income',
          value: incomeCents,
          fmt: money,
          icon: <TrendingUp className="size-4" />,
          tone: 'positive' as const,
        },
        {
          label: 'Inbox items',
          value: inboxCount,
          fmt: (n: number) => String(Math.round(n)),
          icon: <Inbox className="size-4" />,
          tone: (inboxCount ? 'negative' : 'neutral') as 'negative' | 'neutral',
        },
      ]
    : []

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title="Dashboard"
        subtitle="Monthly credit card spending split between Personal and Work, plus checking income"
      />
      {isLoading || !data ? (
        <Skeleton className="h-80" />
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {stats.map((s, i) => (
              <div
                key={s.label}
                className="animate-[fadeInUp_400ms_var(--ease-out)_both]"
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <StatCard
                  label={s.label}
                  value={s.fmt(s.value)}
                  animateTo={s.value}
                  format={s.fmt}
                  icon={s.icon}
                  tone={s.tone}
                  gradient={s.gradient}
                />
              </div>
            ))}
          </div>
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
        </>
      )}
    </div>
  )
}
