import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { DashboardPage } from './DashboardPage'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="chart">{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}))

describe('DashboardPage', () => {
  it('renders stat cards populated from the dashboard API', async () => {
    renderWithProviders(<DashboardPage />)

    expect(await screen.findByText('$500.00')).toBeInTheDocument()
    expect(screen.getByText('$125.00')).toBeInTheDocument()
    expect(screen.getByText('Personal spending')).toBeInTheDocument()
    expect(screen.getByText('Work spending')).toBeInTheDocument()
  })

  it('renders the chart container after data loads', async () => {
    renderWithProviders(<DashboardPage />)
    expect(await screen.findByTestId('chart')).toBeInTheDocument()
  })

  it('handles an empty dashboard payload without crashing', async () => {
    server.use(
      http.get('/api/v1/transactions/dashboard', () =>
        HttpResponse.json({
          personal_total_cents: 0,
          work_total_cents: 0,
          unsorted_count: 0,
          latest_month: null,
          months: [],
          income_total_cents: 0,
          reimbursement_total_cents: 0,
          uncategorized_income_cents: 0,
          uncategorized_income_count: 0,
        }),
      ),
    )
    renderWithProviders(<DashboardPage />)
    expect(await screen.findAllByText('$0.00')).not.toHaveLength(0)
  })

  it('renders the new insight cards from dashboard data', async () => {
    renderWithProviders(<DashboardPage />)

    // Net cash flow = income 200000 - personal 50000 = 150000
    expect(await screen.findByText('Net cash flow')).toBeInTheDocument()
    expect(screen.getByText('$1,500.00')).toBeInTheDocument()
    expect(screen.getByText('Saving 75% of income')).toBeInTheDocument()

    // Awaiting reimbursement = 8000 cents, 2 items
    expect(screen.getByText('Awaiting reimbursement')).toBeInTheDocument()
    expect(screen.getByText('$80.00')).toBeInTheDocument()
    expect(screen.getByText(/2 items to expense/i)).toBeInTheDocument()

    // Top merchants
    expect(screen.getByText('Top merchants')).toBeInTheDocument()
    expect(screen.getByText('WHOLE FOODS MKT')).toBeInTheDocument()
    expect(screen.getByText('STARBUCKS')).toBeInTheDocument()
  })

  it('shows month-over-month spending change', async () => {
    renderWithProviders(<DashboardPage />)
    // months: 04 = 30000 -> 05 = 20000, a 33% decrease
    expect(await screen.findByText(/less vs last month/i)).toBeInTheDocument()
  })

  it('re-queries with the selected range from the segmented control', async () => {
    const monthsSeen: string[] = []
    server.use(
      http.get('/api/v1/transactions/dashboard', ({ request }) => {
        monthsSeen.push(new URL(request.url).searchParams.get('months') ?? '')
        return HttpResponse.json({
          personal_total_cents: 0,
          work_total_cents: 0,
          unsorted_count: 0,
          latest_month: null,
          months: [],
          income_total_cents: 0,
          reimbursement_total_cents: 0,
          uncategorized_income_cents: 0,
          uncategorized_income_count: 0,
          unexpensed_work_cents: 0,
          unexpensed_work_count: 0,
          top_merchants: [],
        })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DashboardPage />)

    await waitFor(() => expect(monthsSeen).toContain('12'))
    await user.click(screen.getByRole('tab', { name: '6m' }))
    await waitFor(() => expect(monthsSeen).toContain('6'))
  })
})
