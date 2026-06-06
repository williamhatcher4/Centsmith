import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { mockSpending } from '../test/handlers'
import { renderWithProviders } from '../test/renderWithProviders'
import type { SpendingByCategory } from '../types'
import { SpendingPage } from './SpendingPage'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="chart">{children}</div>,
  BarChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
}))

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (importActual) => {
  const actual = await importActual<typeof import('react-router-dom')>()
  return { ...actual, useNavigate: () => navigateMock }
})

/** Override the spending endpoint so the latest (default-selected) month is `label` with one category. */
function useSpendingMonth(label: string, category: SpendingByCategory) {
  server.use(
    http.get('/api/v1/transactions/spending/personal', () =>
      HttpResponse.json({ ...mockSpending, points: [{ label, amount_cents: category.amount_cents, by_category: [category] }] }),
    ),
  )
}

describe('SpendingPage', () => {
  it('renders totals and the by-category breakdown from the spending API', async () => {
    renderWithProviders(<SpendingPage />)

    expect(await screen.findByText('Total personal')).toBeInTheDocument()
    expect(screen.getByText('Monthly average')).toBeInTheDocument()
    expect(screen.getAllByText('$500.00').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Dining').length).toBeGreaterThan(0)
  })

  it('updates query when months selector changes', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SpendingPage />)

    await screen.findByText('Total personal')
    const sixMonth = screen.getByRole('tab', { name: '6m' })
    await user.click(sixMonth)
    await waitFor(() => expect(sixMonth).toHaveAttribute('aria-selected', 'true'))
  })

  describe('category drill-down', () => {
    it('navigates to the transactions page filtered by category and month when a per-month category is clicked', async () => {
      navigateMock.mockClear()
      const user = userEvent.setup()
      // Default selection is the latest point: 2026-05 / Dining (a 31-day month).
      renderWithProviders(<SpendingPage />)

      const btn = await screen.findByRole('button', { name: 'View Dining transactions for 2026-05' })
      await user.click(btn)

      expect(navigateMock).toHaveBeenCalledWith(
        '/transactions?classification=personal&personal_category=Dining&start_date=2026-05-01&end_date=2026-05-31',
      )
    })

    it('maps the Uncategorized bucket to personal_category=uncategorized and clamps February', async () => {
      navigateMock.mockClear()
      useSpendingMonth('2026-02', { category_name: 'Uncategorized', amount_cents: 5000, percent: 100 })
      const user = userEvent.setup()
      renderWithProviders(<SpendingPage />)

      const btn = await screen.findByRole('button', { name: 'View Uncategorized transactions for 2026-02' })
      await user.click(btn)

      expect(navigateMock).toHaveBeenCalledWith(
        '/transactions?classification=personal&personal_category=uncategorized&start_date=2026-02-01&end_date=2026-02-28',
      )
    })

    it('computes the last day for a 30-day month', async () => {
      navigateMock.mockClear()
      useSpendingMonth('2026-04', { category_name: 'Groceries', amount_cents: 5000, percent: 100 })
      const user = userEvent.setup()
      renderWithProviders(<SpendingPage />)

      const btn = await screen.findByRole('button', { name: 'View Groceries transactions for 2026-04' })
      await user.click(btn)

      expect(navigateMock).toHaveBeenCalledWith(
        '/transactions?classification=personal&personal_category=Groceries&start_date=2026-04-01&end_date=2026-04-30',
      )
    })
  })
})
