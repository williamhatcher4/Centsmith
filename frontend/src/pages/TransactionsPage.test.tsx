import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { mockManualTransaction, mockTransactions, pageOf } from '../test/handlers'
import { renderWithProviders } from '../test/renderWithProviders'
import { TransactionsPage } from './TransactionsPage'

describe('TransactionsPage', () => {
  it('shows the empty state when no transactions match the default filters', async () => {
    renderWithProviders(<TransactionsPage />)
    expect(await screen.findByText('No transactions')).toBeInTheDocument()
  })

  it('hides the Expensed filter unless the work classification is active', async () => {
    server.use(
      http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
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

  it('initializes filters from URL search params (deep link)', async () => {
    const calls: string[] = []
    server.use(
      http.get('/api/v1/transactions', ({ request }) => {
        calls.push(new URL(request.url).search)
        return HttpResponse.json(pageOf([]))
      }),
    )
    renderWithProviders(<TransactionsPage />, { route: '/transactions?classification=work&expensed=unexpensed' })

    // Type select reflects the URL, and the work-only Expensed filter is shown.
    expect(await screen.findByLabelText('Expensed')).toBeInTheDocument()
    expect((screen.getByLabelText('Type') as HTMLSelectElement).value).toBe('work')

    await waitFor(() => {
      const latest = calls[calls.length - 1]
      expect(latest).toContain('classification=work')
      expect(latest).toContain('expensed=false')
    })
  })

  it('initializes the date range and category from URL search params (deep link)', async () => {
    const calls: string[] = []
    server.use(
      http.get('/api/v1/transactions', ({ request }) => {
        calls.push(new URL(request.url).search)
        return HttpResponse.json(pageOf([]))
      }),
    )
    renderWithProviders(<TransactionsPage />, { route: '/transactions?classification=personal&personal_category=Groceries&start_date=2026-05-01&end_date=2026-05-31' })

    // Date inputs reflect the URL params...
    expect((await screen.findByLabelText('From') as HTMLInputElement).value).toBe('2026-05-01')
    expect((screen.getByLabelText('To') as HTMLInputElement).value).toBe('2026-05-31')
    expect((screen.getByLabelText('Category') as HTMLSelectElement).value).toBe('Groceries')

    // ...and flow through to the API request.
    await waitFor(() => {
      const latest = calls[calls.length - 1]
      expect(latest).toContain('start_date=2026-05-01')
      expect(latest).toContain('end_date=2026-05-31')
      expect(latest).toContain('personal_category=Groceries')
    })
  })

  it('ignores malformed date params from the URL', async () => {
    renderWithProviders(<TransactionsPage />, { route: '/transactions?start_date=not-a-date&end_date=05%2F31%2F2026' })
    expect((await screen.findByLabelText('From') as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText('To') as HTMLInputElement).value).toBe('')
  })

  it('auto-opens the add modal from the action URL param', async () => {
    renderWithProviders(<TransactionsPage />, { route: '/transactions?action=add' })
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByLabelText('Description')).toBeInTheDocument()
  })

  it('passes start_date and end_date to the API when the user picks them', async () => {
    const calls: string[] = []
    server.use(
      http.get('/api/v1/transactions', ({ request }) => {
        calls.push(new URL(request.url).search)
        return HttpResponse.json(pageOf([]))
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

  it('loads more rows when the Load more button is clicked', async () => {
    const rowB = { ...mockTransactions[1], id: 2, description: 'Second page row' }
    server.use(
      http.get('/api/v1/transactions', ({ request }) => {
        const skip = Number(new URL(request.url).searchParams.get('skip') ?? '0')
        if (skip === 0) {
          return HttpResponse.json({ items: [mockTransactions[0]], total: 2, skip: 0, limit: 1, has_more: true, next_skip: 1 })
        }
        return HttpResponse.json({ items: [rowB], total: 2, skip: 1, limit: 1, has_more: false, next_skip: null })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<TransactionsPage />)

    await screen.findByText('Coffee shop')
    expect(screen.getByText(/Showing 1 of 2/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /load more/i }))

    // Both pages are now visible and the control disappears once fully loaded.
    expect(await screen.findByText('Second page row')).toBeInTheDocument()
    expect(screen.getByText('Coffee shop')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument()
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
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
      )
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')
      const deleteBtns = screen.getAllByRole('button', { name: /delete/i })
      expect(deleteBtns.length).toBe(mockTransactions.length)
    })

    it('shows confirmation dialog before deleting', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
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
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
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
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf([mockManualTransaction]))),
      )
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Manual entry')
      expect(screen.getByText('Manual')).toBeInTheDocument()
    })

    it('invalidates import history after deleting a transaction', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
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

  // ---------------------------------------------------------------------------
  // Edit transaction (classification + category)
  // ---------------------------------------------------------------------------

  describe('Edit transaction', () => {
    it('shows an edit button for each transaction row', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
      )
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')
      expect(screen.getAllByRole('button', { name: /edit/i })).toHaveLength(mockTransactions.length)
    })

    it('opens a pre-filled edit modal and reveals the category select for personal rows', async () => {
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
      )
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')

      await user.click(screen.getAllByRole('button', { name: /edit/i })[0])
      const dialog = await screen.findByRole('dialog')
      // The row being edited is summarized; classification starts unset, so no category yet.
      expect(within(dialog).getByText('Coffee shop')).toBeInTheDocument()
      expect(screen.queryByLabelText('Category')).not.toBeInTheDocument()

      await user.selectOptions(screen.getByLabelText('Classification'), 'personal')
      expect(await screen.findByLabelText('Category')).toBeInTheDocument()
    })

    it('saves classification + category via PUT and closes the modal', async () => {
      let body: Record<string, unknown> | null = null
      server.use(
        http.get('/api/v1/transactions', () => HttpResponse.json(pageOf(mockTransactions))),
        http.put('/api/v1/transactions/:id', async ({ request }) => {
          body = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({ ...mockTransactions[0], classification: 'personal', personal_category: 'Dining' })
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<TransactionsPage />)
      await screen.findByText('Coffee shop')

      await user.click(screen.getAllByRole('button', { name: /edit/i })[0])
      await screen.findByRole('dialog')
      await user.selectOptions(screen.getByLabelText('Classification'), 'personal')
      await user.selectOptions(await screen.findByLabelText('Category'), 'Dining')
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
      expect(body).toEqual({ classification: 'personal', personal_category: 'Dining', expensed: false, card_id: null })
    })
  })
})
