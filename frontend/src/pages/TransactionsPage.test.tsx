import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { mockManualTransaction, mockTransactions } from '../test/handlers'
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

  // ---------------------------------------------------------------------------
  // Phase 1: Add transaction modal
  // ---------------------------------------------------------------------------

  describe('Add transaction', () => {
    it('opens the add modal when the Add button is clicked', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await user.click(screen.getByRole('button', { name: /add/i }))
      expect(await screen.findByRole('dialog')).toBeInTheDocument()
      expect(screen.getByLabelText('Description')).toBeInTheDocument()
    })

    it('closes the modal when Cancel is clicked', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await user.click(screen.getByRole('button', { name: /add/i }))
      await screen.findByRole('dialog')
      await user.click(screen.getByRole('button', { name: /cancel/i }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })

    it('shows validation error when description is empty', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await user.click(screen.getByRole('button', { name: /add/i }))
      await screen.findByRole('dialog')
      await user.type(screen.getByLabelText('Amount ($)'), '10')
      await user.click(screen.getByRole('button', { name: /save/i }))
      expect(await screen.findByText('Description is required')).toBeInTheDocument()
    })

    it('shows validation error when amount is missing', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await user.click(screen.getByRole('button', { name: /add/i }))
      await screen.findByRole('dialog')
      await user.type(screen.getByLabelText('Description'), 'Coffee')
      await user.click(screen.getByRole('button', { name: /save/i }))
      expect(await screen.findByText('Enter a positive amount')).toBeInTheDocument()
    })

    it('submits the form and closes modal on success', async () => {
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await user.click(screen.getByRole('button', { name: /add/i }))
      await screen.findByRole('dialog')
      await user.type(screen.getByLabelText('Description'), 'Test entry')
      await user.type(screen.getByLabelText('Amount ($)'), '12.50')
      await user.click(screen.getByRole('button', { name: /save/i }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    })
  })

  // ---------------------------------------------------------------------------
  // Phase 1: Delete transaction
  // ---------------------------------------------------------------------------

  describe('Delete transaction', () => {
    it('shows delete button for each transaction row', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(mockTransactions)),
      )
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')
      const deleteBtns = screen.getAllByRole('button', { name: /delete/i })
      expect(deleteBtns.length).toBe(mockTransactions.length)
    })

    it('shows confirmation dialog before deleting', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(mockTransactions)),
      )
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')
      await user.click(screen.getAllByRole('button', { name: /delete/i })[0])
      expect(await screen.findByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/delete transaction/i)).toBeInTheDocument()
    })

    it('does not delete when cancel is clicked in the confirm dialog', async () => {
      const calls: string[] = []
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(mockTransactions)),
        http.delete('/api/v1/transactions/:id', ({ params }) => {
          calls.push(String(params.id))
          return HttpResponse.json(mockTransactions[0])
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')
      await user.click(screen.getAllByRole('button', { name: /delete/i })[0])
      await screen.findByRole('dialog')
      await user.click(screen.getByRole('button', { name: /cancel/i }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(calls).toHaveLength(0)
    })

    it('shows Manual badge for manually-created transactions', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json([mockManualTransaction])),
      )
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Manual entry')
      expect(screen.getByText('Manual')).toBeInTheDocument()
    })

    it('invalidates import history after deleting a transaction', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(mockTransactions)),
        http.delete('/api/v1/transactions/:id', () => HttpResponse.json(mockTransactions[0])),
      )
      const user = userEvent.setup()
      const { queryClient } = renderWithProviders(<TransactionsPage />)
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

      await screen.findByText('Coffee shop')
      await user.click(screen.getAllByRole('button', { name: /delete/i })[0])
      await screen.findByRole('dialog')
      await user.click(screen.getByRole('button', { name: /^delete$/i }))

      await waitFor(() => {
        expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['imports'] })
      })
    })
  })
})
