import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/renderWithProviders'
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
})
