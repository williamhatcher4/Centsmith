import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { mockTransactions } from '../test/handlers'
import { renderWithProviders } from '../test/renderWithProviders'
import { TransactionsPage } from './TransactionsPage'

describe('TransactionsPage', () => {
  it('shows the empty state when no transactions match the default filters', async () => {
    renderWithProviders(<TransactionsPage />)
    expect(await screen.findByText('No transactions')).toBeInTheDocument()
  })

  it('hides the Expensed filter unless the work classification is active', async () => {
    server.use(
      http.get('/api/v1/transactions', () => HttpResponse.json(mockTransactions)),
    )
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await screen.findByText('Coffee shop')
    expect(screen.queryByLabelText('Expensed')).not.toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Type'), 'work')
    expect(await screen.findByLabelText('Expensed')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Type'), 'personal')
    await waitFor(() => expect(screen.queryByLabelText('Expensed')).not.toBeInTheDocument())
    expect(screen.getByLabelText('Category')).toBeInTheDocument()
  })

  it('passes start_date and end_date to the API when the user picks them', async () => {
    const calls: string[] = []
    server.use(
      http.get('/api/v1/transactions', ({ request }) => {
        calls.push(new URL(request.url).search)
        return HttpResponse.json([])
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await waitFor(() => expect(calls.length).toBeGreaterThan(0))
    const before = calls.length
    await user.type(screen.getByLabelText('From'), '2026-05-01')
    await user.type(screen.getByLabelText('To'), '2026-05-31')

    await waitFor(() => {
      const latest = calls[calls.length - 1]
      expect(latest).toContain('start_date=2026-05-01')
      expect(latest).toContain('end_date=2026-05-31')
    })
    expect(calls.length).toBeGreaterThan(before)
  })
})
