import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Inbox, BriefcaseBusiness, TrendingUp, WalletCards } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import { formatMoney } from '../utils/money'
import { Card, CardHeader, PageHeader, Skeleton, StatCard } from '../components/ui'

export function DashboardPage() {
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: transactionsApi.dashboard })
  const chartData = data?.months.map((m) => ({
    month: m.month,
    Personal: m.personal_cents / 100,
    Work: m.work_cents / 100,
    Income: (m.income_cents + m.reimbursement_cents) / 100,
  })) ?? []

  return <div>
    <PageHeader title="Dashboard" subtitle="Monthly credit card spending split between Personal and Work, plus checking income" />
    {isLoading || !data ? <Skeleton className="h-80" /> : <>
      <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Personal spending" value={formatMoney(data.personal_total_cents)} icon={<WalletCards className="size-4" />} />
        <StatCard label="Work spending" value={formatMoney(data.work_total_cents)} icon={<BriefcaseBusiness className="size-4" />} tone="accent" />
        <StatCard label="Income" value={formatMoney(data.income_total_cents + data.reimbursement_total_cents)} icon={<TrendingUp className="size-4" />} tone="positive" />
        <StatCard label="Inbox items" value={String(data.unsorted_count + data.uncategorized_income_count)} icon={<Inbox className="size-4" />} tone={data.unsorted_count + data.uncategorized_income_count ? 'negative' : 'neutral'} />
      </div>
      <Card padding="md">
        <CardHeader title="Personal, Work, and Income by month" subtitle={data.latest_month ? `Latest month: ${data.latest_month}` : 'No classified activity yet'} />
        <div className="h-[360px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
              <XAxis dataKey="month" tick={{ fill: 'var(--text-subtle)', fontSize: 12 }} />
              <YAxis tick={{ fill: 'var(--text-subtle)', fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
              <Tooltip formatter={(v) => formatMoney(Math.round(Number(v) * 100))} contentStyle={{ background: 'var(--surface-solid)', border: '1px solid var(--border)', borderRadius: 8 }} />
              <Bar dataKey="Personal" fill="var(--chart-3)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Work" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Income" fill="var(--success)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </>}
  </div>
}

