import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
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
})
