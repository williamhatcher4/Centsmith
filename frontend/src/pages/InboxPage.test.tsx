import { describe, expect, it } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { mockTransactions } from '../test/handlers'
import { renderWithProviders } from '../test/renderWithProviders'
import { InboxPage } from './InboxPage'

describe('InboxPage', () => {
  it('renders unsorted transactions returned by the API', async () => {
    renderWithProviders(<InboxPage />)

    expect(await screen.findByText('Coffee shop')).toBeInTheDocument()
    expect(screen.getByText('Grocery store')).toBeInTheDocument()
    expect(screen.getByText('Open items')).toBeInTheDocument()
  })

  it('filters by description as the user types', async () => {
    const user = userEvent.setup()
    renderWithProviders(<InboxPage />)

    await screen.findByText('Coffee shop')
    await user.type(screen.getByPlaceholderText('Description'), 'grocery')

    await waitFor(() => expect(screen.queryByText('Coffee shop')).not.toBeInTheDocument())
    expect(screen.getByText('Grocery store')).toBeInTheDocument()
  })

  it('disables Apply until both a selection and bulk classification are picked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<InboxPage />)

    await screen.findByText('Coffee shop')
    const applyButton = screen.getByRole('button', { name: /Apply to 0/i })
    expect(applyButton).toBeDisabled()

    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[1])
    expect(screen.getByRole('button', { name: /Apply to 1/i })).toBeDisabled()

    await user.selectOptions(screen.getByLabelText('Bulk sort'), 'personal')
    expect(screen.getByRole('button', { name: /Apply to 1/i })).toBeEnabled()
  })

  it('invokes bulk-classify and refetches when Apply is clicked', async () => {
    const calls: string[] = []
    server.use(
      http.post('/api/v1/transactions/bulk-classify', async ({ request }) => {
        calls.push(await request.text())
        return HttpResponse.json({ updated: 1 })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<InboxPage />)

    await screen.findByText('Coffee shop')
    const checkboxes = screen.getAllByRole('checkbox')
    await user.click(checkboxes[1])
    await user.selectOptions(screen.getByLabelText('Bulk sort'), 'work')
    await user.click(screen.getByRole('button', { name: /Apply to 1/i }))

    await waitFor(() => expect(calls.length).toBe(1))
    expect(JSON.parse(calls[0])).toMatchObject({ transaction_ids: [mockTransactions[0].id], classification: 'work' })
  })

  describe('keyboard triage', () => {
    it('classifies the focused row with the w shortcut', async () => {
      const calls: string[] = []
      server.use(
        http.post('/api/v1/transactions/bulk-classify', async ({ request }) => {
          calls.push(await request.text())
          return HttpResponse.json({ updated: 1 })
        }),
      )
      renderWithProviders(<InboxPage />)
      await screen.findByText('Coffee shop')

      fireEvent.keyDown(window, { key: 'w' })
      await waitFor(() => expect(calls.length).toBe(1))
      expect(JSON.parse(calls[0])).toMatchObject({ transaction_ids: [mockTransactions[0].id], classification: 'work' })
    })

    it('focuses the search field when / is pressed', async () => {
      renderWithProviders(<InboxPage />)
      await screen.findByText('Coffee shop')

      fireEvent.keyDown(window, { key: '/' })
      expect(document.activeElement).toBe(screen.getByPlaceholderText('Description'))
    })

    it('does not fire shortcuts while typing in the search field', async () => {
      const calls: string[] = []
      server.use(
        http.post('/api/v1/transactions/bulk-classify', async ({ request }) => {
          calls.push(await request.text())
          return HttpResponse.json({ updated: 1 })
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<InboxPage />)
      await screen.findByText('Coffee shop')

      const searchInput = screen.getByPlaceholderText('Description') as HTMLInputElement
      searchInput.focus()
      await user.type(searchInput, 'w')

      expect(calls).toHaveLength(0)
      expect(searchInput.value).toBe('w')
    })
  })
})
