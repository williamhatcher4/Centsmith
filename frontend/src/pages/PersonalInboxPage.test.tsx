import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { pageOf } from '../test/handlers'
import { renderWithProviders } from '../test/renderWithProviders'
import { PersonalInboxPage } from './PersonalInboxPage'
import type { Transaction } from '../types'

const personalDebit: Transaction = {
  id: 10,
  transaction_date: '2026-05-01',
  description: 'Grocery store',
  amount_cents: 4200,
  transaction_type: 'debit',
  classification: 'personal',
  personal_category: null,
  expensed: false,
  is_manual: false,
  statement_format: 'test',
  imported_at: '2026-05-01T12:00:00Z',
}

const personalCredit: Transaction = {
  ...personalDebit,
  id: 11,
  description: 'Refund Amazon',
  amount_cents: 1500,
  transaction_type: 'credit',
}

describe('PersonalInboxPage', () => {
  it('shows debit-only spending categories when only debits are selected', async () => {
    server.use(http.get('/api/v1/transactions', () => HttpResponse.json(pageOf([personalDebit, personalCredit]))))
    const user = userEvent.setup()
    renderWithProviders(<PersonalInboxPage />)

    await screen.findByText('Grocery store')
    const rowCheckboxes = screen.getAllByRole('checkbox').slice(1)
    await user.click(rowCheckboxes[0])

    const bulkSelect = screen.getByLabelText('Bulk category') as HTMLSelectElement
    const optionValues = Array.from(bulkSelect.options).map((opt) => opt.value)
    expect(optionValues).toContain('Groceries')
    expect(optionValues).not.toContain('Income')
  })

  it('includes Income categories when only credits are selected', async () => {
    server.use(http.get('/api/v1/transactions', () => HttpResponse.json(pageOf([personalDebit, personalCredit]))))
    const user = userEvent.setup()
    renderWithProviders(<PersonalInboxPage />)

    await screen.findByText('Grocery store')
    const rowCheckboxes = screen.getAllByRole('checkbox').slice(1)
    await user.click(rowCheckboxes[1])

    const bulkSelect = screen.getByLabelText('Bulk category') as HTMLSelectElement
    const optionValues = Array.from(bulkSelect.options).map((opt) => opt.value)
    expect(optionValues).toContain('Income')
    expect(optionValues).toContain('Reimbursement')
    expect(optionValues).toContain('Groceries')
  })

  it('restricts the bulk select to Transfer when mixing credit and debit selections', async () => {
    server.use(http.get('/api/v1/transactions', () => HttpResponse.json(pageOf([personalDebit, personalCredit]))))
    const user = userEvent.setup()
    renderWithProviders(<PersonalInboxPage />)

    await screen.findByText('Grocery store')
    const rowCheckboxes = screen.getAllByRole('checkbox').slice(1)
    await user.click(rowCheckboxes[0])
    await user.click(rowCheckboxes[1])

    const bulkSelect = screen.getByLabelText('Bulk category') as HTMLSelectElement
    const optionValues = Array.from(bulkSelect.options).map((opt) => opt.value).filter(Boolean)
    expect(optionValues).toEqual(['Transfer'])
  })

  it('submits a categorize request when a per-row category is chosen', async () => {
    const calls: unknown[] = []
    server.use(
      http.get('/api/v1/transactions', () => HttpResponse.json(pageOf([personalDebit]))),
      http.post('/api/v1/transactions/bulk-categorize-personal', async ({ request }) => {
        calls.push(await request.json())
        return HttpResponse.json({ updated: 1 })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<PersonalInboxPage />)

    await screen.findByText('Grocery store')
    await user.selectOptions(screen.getByLabelText('Category for Grocery store'), 'Groceries')

    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]).toEqual({ transaction_ids: [personalDebit.id], personal_category: 'Groceries' })
  })
})
