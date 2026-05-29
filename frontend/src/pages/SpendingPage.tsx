import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { transactionsApi } from '../api/transactions'
import type { SpendingByCategory } from '../types'
import { formatMoney } from '../utils/money'
import { Card, CardHeader, PageHeader, SegmentedControl, Skeleton, StatCard } from '../components/ui'
import { useReducedMotion } from '../hooks/useReducedMotion'

const money = (n: number) => formatMoney(Math.round(n))

const CATEGORY_COLORS = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--chart-6)']

function colorFor(index: number) {
  return CATEGORY_COLORS[index % CATEGORY_COLORS.length]
}

function CategoryRow({ category, color, perMonthCents }: { category: SpendingByCategory; color: string; perMonthCents?: number }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span aria-hidden="true" className="size-2.5 shrink-0 rounded-full" style={{ background: color }} />
          <span className="truncate text-sm font-medium text-[var(--text)]">{category.category_name}</span>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold tabular-nums text-[var(--text)]">{formatMoney(category.amount_cents)}</div>
          {perMonthCents !== undefined && <div className="text-[11px] text-[var(--text-faint)]">{formatMoney(perMonthCents)} per month</div>}
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div className="h-full rounded-full transition-[width] duration-500 ease-[var(--ease-out)]" style={{ width: `${Math.max(0, Math.min(100, category.percent))}%`, background: color }} />
      </div>
      <div className="mt-1 text-[11px] text-[var(--text-faint)]">{category.percent.toFixed(1)}%</div>
    </div>
  )
}

export function SpendingPage() {
  const reduced = useReducedMotion()
  const [months, setMonths] = useState(12)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['spending', months], queryFn: () => transactionsApi.personalSpending(months) })
  const { data: income } = useQuery({ queryKey: ['income', months], queryFn: () => transactionsApi.personalIncome(months) })
  const points = data?.points ?? []
  const byCategory = data?.by_category ?? []
  const incomeByCategory = income?.by_category ?? []
  const chartData = points.map((p) => ({ month: p.label, amount: p.amount_cents / 100 }))
  const selectedIndex = hoverIndex ?? points.length - 1
  const hoveredPoint = selectedIndex >= 0 && selectedIndex < points.length ? points[selectedIndex] : null
  const hoveredCategories = hoveredPoint?.by_category ?? []

  return (
    <div>
      <PageHeader eyebrow="Insights" title="Personal Spending" subtitle="Monthly personal spending with category breakdowns" />
      <div className="mb-5">
        <SegmentedControl
          value={months}
          onChange={(value) => {
            setMonths(value)
            setHoverIndex(null)
          }}
          options={[{ label: '6m', value: 6 }, { label: '12m', value: 12 }, { label: '24m', value: 24 }]}
        />
      </div>

      {isLoading || !data ? (
        <Skeleton className="h-80" />
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-3">
            <div className="animate-[fadeInUp_400ms_var(--ease-out)_both]">
              <StatCard label="Total personal" value={formatMoney(data.total_cents)} animateTo={data.total_cents} format={money} gradient />
            </div>
            <div className="animate-[fadeInUp_400ms_var(--ease-out)_both]" style={{ animationDelay: '60ms' }}>
              <StatCard label="Monthly average" value={formatMoney(data.average_per_month_cents)} animateTo={data.average_per_month_cents} format={money} tone="accent" />
            </div>
            <div className="animate-[fadeInUp_400ms_var(--ease-out)_both]" style={{ animationDelay: '120ms' }}>
              <StatCard label="Months" value={String(points.length)} animateTo={points.length} format={(n) => String(Math.round(n))} tone="neutral" />
            </div>
          </div>

          {income && income.total_cents > 0 && (
            <Card variant="solid" padding="md" className="mb-6">
              <CardHeader title="Income" subtitle={`${formatMoney(income.total_cents)} total · ${formatMoney(income.average_per_month_cents)} per month`} />
              {incomeByCategory.length === 0 ? (
                <p className="text-sm text-[var(--text-subtle)]">No categorized income yet.</p>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  {incomeByCategory.map((category, index) => (
                    <CategoryRow key={category.category_name} category={category} color={colorFor(index)} perMonthCents={Math.round(category.amount_cents / Math.max(income.points.length, 1))} />
                  ))}
                </div>
              )}
            </Card>
          )}

          <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
            <div className="flex flex-col gap-6">
              <Card padding="md">
                <CardHeader title="Personal expenses by month" />
                <div className="h-[360px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={chartData}
                      margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                      onMouseMove={(state) => { if (state.activeTooltipIndex != null) setHoverIndex(Number(state.activeTooltipIndex)) }}
                    >
                      <defs>
                        <linearGradient id="spendBar" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="var(--chart-3)" stopOpacity={0.95} />
                          <stop offset="100%" stopColor="var(--chart-3)" stopOpacity={0.5} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis dataKey="month" tick={{ fill: 'var(--text-subtle)', fontSize: 12 }} />
                      <YAxis tick={{ fill: 'var(--text-subtle)', fontSize: 12 }} tickFormatter={(v) => `$${v}`} />
                      <Tooltip formatter={(v) => formatMoney(Math.round(Number(v) * 100))} contentStyle={{ background: 'var(--surface-strong)', border: '1px solid var(--border-strong)', borderRadius: 12, backdropFilter: 'var(--blur-glass)', boxShadow: 'var(--shadow-md)' }} cursor={{ fill: 'var(--accent-soft)' }} />
                      <Bar dataKey="amount" fill="url(#spendBar)" radius={[5, 5, 0, 0]} isAnimationActive={!reduced} animationDuration={700} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              <Card variant="solid" padding="md">
                <CardHeader title={hoveredPoint ? hoveredPoint.label : 'No data'} actions={hoveredPoint ? <span className="text-sm font-bold tabular-nums text-[var(--text)]">{formatMoney(hoveredPoint.amount_cents)}</span> : undefined} />
                {hoveredCategories.length === 0 ? (
                  <p className="text-sm text-[var(--text-subtle)]">No personal spending in this month.</p>
                ) : (
                  <div key={hoveredPoint?.label} className="flex flex-col gap-4 animate-[fadeIn_220ms_var(--ease-out)]">
                    {hoveredCategories.map((category, index) => <CategoryRow key={category.category_name} category={category} color={colorFor(index)} />)}
                  </div>
                )}
              </Card>
            </div>

            <Card variant="solid" padding="md">
              <CardHeader title="By Category" subtitle="Selected range" />
              {byCategory.length === 0 ? (
                <p className="text-sm text-[var(--text-subtle)]">No personal expenses yet.</p>
              ) : (
                <div className="flex flex-col gap-4">
                  {byCategory.map((category, index) => (
                    <CategoryRow key={category.category_name} category={category} color={colorFor(index)} perMonthCents={Math.round(category.amount_cents / Math.max(points.length, 1))} />
                  ))}
                </div>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
