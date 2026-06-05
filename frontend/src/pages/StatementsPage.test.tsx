import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { StatementsPage } from './StatementsPage'

describe('StatementsPage', () => {
  it('shows charges, payments, and net for the selected card', async () => {
    server.use(
      http.get('/api/v1/cards/:id/statement', () =>
        HttpResponse.json({
          card_id: 1,
          start_date: '2026-04-22',
          end_date: '2026-05-21',
          charges_cents: 2450000,
          payments_cents: 43508,
          net_cents: 2406492,
          charge_count: 12,
          payment_count: 1,
        }),
      ),
    )
    renderWithProviders(<StatementsPage />)
    expect(await screen.findByText('Amex Platinum')).toBeInTheDocument()
    // Distinct figures for charges / payments / net (render after the statement loads).
    expect(await screen.findByText('$24,500.00')).toBeInTheDocument()
    expect(await screen.findByText('$435.08')).toBeInTheDocument()
    expect(await screen.findByText('$24,064.92')).toBeInTheDocument()
    expect(screen.getByText('Charges')).toBeInTheDocument()
    expect(screen.getByText('Payments / credits')).toBeInTheDocument()
    expect(screen.getByText('Net this statement')).toBeInTheDocument()
  })

  it('confirms a matching bank figure and flags a mismatch', async () => {
    const user = userEvent.setup()
    renderWithProviders(<StatementsPage />)
    const input = await screen.findByLabelText('Bank statement figure')

    await user.type(input, '24064.92')
    expect(await screen.findByText(/Matches net/)).toBeInTheDocument()

    await user.clear(input)
    await user.type(input, '24000.00')
    expect(await screen.findByText(/Off by/)).toBeInTheDocument()
  })

  it('renders an empty state when there are no cards', async () => {
    server.use(http.get('/api/v1/cards', () => HttpResponse.json([])))
    renderWithProviders(<StatementsPage />)
    expect(await screen.findByText('No cards yet')).toBeInTheDocument()
  })

  it('creates a card from the add modal', async () => {
    const user = userEvent.setup()
    let posted = false
    server.use(
      http.get('/api/v1/cards', () => HttpResponse.json([])),
      http.post('/api/v1/cards', async () => {
        posted = true
        return HttpResponse.json({ id: 2, name: 'Visa', last4: '4242', statement_day: 10 }, { status: 201 })
      }),
    )
    renderWithProviders(<StatementsPage />)
    const addButtons = await screen.findAllByRole('button', { name: /add card/i })
    await user.click(addButtons[0])
    await user.type(await screen.findByLabelText('Card name'), 'Visa')
    await user.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted).toBe(true))
  })
})
