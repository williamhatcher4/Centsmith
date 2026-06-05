import { beforeEach, describe, expect, it } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { SettingsPage } from './SettingsPage'
import type { UserSettings } from '../types'

const DEFAULT_SETTINGS: UserSettings = {
  personal_categories: [
    'Groceries', 'Dining', 'Transportation', 'Home', 'Health',
    'Subscriptions', 'Shopping', 'Travel', 'Entertainment',
    'Personal Care', 'Gifts', 'Other', 'Transfer', 'Income', 'Reimbursement',
  ],
  hidden_pages: [],
}

describe('SettingsPage', () => {
  it('renders all categories with system badges on protected ones', async () => {
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    expect(screen.getByText('Income')).toBeInTheDocument()
    expect(screen.getByText('Reimbursement')).toBeInTheDocument()
    expect(screen.getByText('Transfer')).toBeInTheDocument()
    // Three system badges
    expect(screen.getAllByText(/^System$/)).toHaveLength(3)
  })

  it('disables rename and delete for system categories', async () => {
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    expect(screen.getByRole('button', { name: 'Rename Income' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Delete Income' })).toBeDisabled()
  })

  it('adds a new category via the add button', async () => {
    let putBody: UserSettings | null = null
    server.use(
      http.put('/api/v1/settings', async ({ request }) => {
        putBody = (await request.json()) as UserSettings
        return HttpResponse.json(putBody)
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    await user.type(screen.getByLabelText(/new category name/i), 'Coffee')
    await user.click(screen.getByRole('button', { name: /^add$/i }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.personal_categories).toContain('Coffee')
  })

  it('rejects duplicate category names client-side', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    await user.type(screen.getByLabelText(/new category name/i), 'Groceries')
    await user.click(screen.getByRole('button', { name: /^add$/i }))

    expect(await screen.findByText(/already exists/i)).toBeInTheDocument()
  })

  it('renames a category via inline edit (sends relabel_target)', async () => {
    let putUrl = ''
    let putBody: UserSettings | null = null
    server.use(
      http.put('/api/v1/settings', async ({ request }) => {
        putUrl = request.url
        putBody = (await request.json()) as UserSettings
        return HttpResponse.json(putBody)
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    await user.click(screen.getByRole('button', { name: 'Rename Groceries' }))
    const input = screen.getByLabelText('Rename Groceries')
    await user.clear(input)
    await user.type(input, 'Food')
    await user.click(screen.getByRole('button', { name: 'Save Groceries' }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.personal_categories).toContain('Food')
    expect(putBody!.personal_categories).not.toContain('Groceries')
    expect(putUrl).toContain('on_delete=relabel')
    expect(putUrl).toContain('relabel_target=Food')
  })

  it('opens delete dialog and confirms a plain delete when category is unused', async () => {
    let putUrl = ''
    let putBody: UserSettings | null = null
    server.use(
      http.put('/api/v1/settings', async ({ request }) => {
        putUrl = request.url
        putBody = (await request.json()) as UserSettings
        return HttpResponse.json(putBody)
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    await user.click(screen.getByRole('button', { name: 'Delete Groceries' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete Groceries' })
    expect(dialog).toHaveTextContent(/No transactions use this category/i)
    await user.click(within(dialog).getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.personal_categories).not.toContain('Groceries')
    expect(putUrl).not.toContain('on_delete=relabel')
  })

  it('opens delete dialog with relabel select when category is in use', async () => {
    server.use(
      http.get('/api/v1/settings/category-usage', () => HttpResponse.json({ Groceries: 3 })),
    )
    let putUrl = ''
    let putBody: UserSettings | null = null
    server.use(
      http.put('/api/v1/settings', async ({ request }) => {
        putUrl = request.url
        putBody = (await request.json()) as UserSettings
        return HttpResponse.json(putBody)
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    await user.click(screen.getByRole('button', { name: 'Delete Groceries' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete Groceries' })
    expect(dialog).toHaveTextContent(/3 transactions use this category/i)
    const targetSelect = within(dialog).getByLabelText('Relabel to') as HTMLSelectElement
    expect(Array.from(targetSelect.options).map((o) => o.value)).not.toContain('Groceries')

    await user.selectOptions(targetSelect, 'Dining')
    await user.click(within(dialog).getByRole('button', { name: /^delete$/i }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putUrl).toContain('on_delete=relabel')
    expect(putUrl).toContain('relabel_target=Dining')
    expect(putBody!.personal_categories).not.toContain('Groceries')
  })

  it('shows usage count next to in-use categories', async () => {
    server.use(
      http.get('/api/v1/settings/category-usage', () => HttpResponse.json({ Dining: 1, Groceries: 5 })),
    )
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')
    expect(await screen.findByText('5 transactions')).toBeInTheDocument()
    expect(await screen.findByText('1 transaction')).toBeInTheDocument()
  })
})

// Sanity: SettingsPage uses mock default settings handler so DEFAULT_SETTINGS must match.
describe('SettingsPage fixture sanity', () => {
  it('mock handlers serve the default categories list', async () => {
    const res = await fetch('/api/v1/settings')
    const data = (await res.json()) as UserSettings
    expect(data.personal_categories).toEqual(DEFAULT_SETTINGS.personal_categories)
  })
})

describe('SettingsPage Pages section', () => {
  it('renders a checkbox per hideable page, all checked by default', async () => {
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')
    expect(screen.getByRole('checkbox', { name: 'Show Dashboard' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Show Inbox' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Show Spending' })).toBeChecked()
    // Settings is not toggle-able
    expect(screen.queryByRole('checkbox', { name: 'Show Settings' })).toBeNull()
  })

  it('disables Save until something changes, then sends the new hidden_pages on save', async () => {
    let putBody: UserSettings | null = null
    server.use(
      http.put('/api/v1/settings', async ({ request }) => {
        putBody = (await request.json()) as UserSettings
        return HttpResponse.json(putBody)
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    const saveBtn = screen.getByRole('button', { name: /save pages/i })
    expect(saveBtn).toBeDisabled()

    await user.click(screen.getByRole('checkbox', { name: 'Show Spending' }))
    expect(saveBtn).toBeEnabled()
    await user.click(saveBtn)

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.hidden_pages).toEqual(['/spending'])
  })

  it('disables the last visible checkbox so the user cannot hide every page', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    // Hide everything except Dashboard. Then Dashboard should be locked.
    for (const label of ['Inbox', 'Personal Inbox', 'Transactions', 'Spending', 'Exports', 'Statements']) {
      await user.click(screen.getByRole('checkbox', { name: `Show ${label}` }))
    }
    const dashboardBox = screen.getByRole('checkbox', { name: 'Show Dashboard' })
    expect(dashboardBox).toBeChecked()
    expect(dashboardBox).toBeDisabled()
    expect(screen.getByText(/at least one page must stay visible/i)).toBeInTheDocument()
  })

  it('resets draft via Cancel button without sending a request', async () => {
    let putCalled = false
    server.use(
      http.put('/api/v1/settings', () => {
        putCalled = true
        return HttpResponse.json({ personal_categories: DEFAULT_SETTINGS.personal_categories, hidden_pages: [] })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Groceries')

    await user.click(screen.getByRole('checkbox', { name: 'Show Exports' }))
    await user.click(screen.getByRole('button', { name: /^cancel$/i }))

    expect(screen.getByRole('checkbox', { name: 'Show Exports' })).toBeChecked()
    expect(screen.getByRole('button', { name: /save pages/i })).toBeDisabled()
    expect(putCalled).toBe(false)
  })
})

describe('SettingsPage appearance', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-accent')
  })

  it('applies the selected accent color', async () => {
    const user = userEvent.setup()
    renderWithProviders(<SettingsPage />)
    await screen.findByText('Appearance')

    const violet = screen.getByRole('button', { name: 'Violet accent' })
    expect(violet).toHaveAttribute('aria-pressed', 'false')
    await user.click(violet)

    expect(document.documentElement.getAttribute('data-accent')).toBe('violet')
    expect(screen.getByRole('button', { name: 'Violet accent' })).toHaveAttribute('aria-pressed', 'true')
  })
})
