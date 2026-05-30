import { describe, expect, it, beforeEach } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { AppShell } from './AppShell'
import { ThemeProvider } from './ui'
import { useAppStore } from '../store/useAppStore'
import type { UserSettings } from '../types'

const DEFAULT_SETTINGS: UserSettings = {
  personal_categories: ['Income', 'Reimbursement', 'Transfer', 'Other'],
  hidden_pages: [],
}

function mountAppShell(route = '/') {
  return renderWithProviders(
    <ThemeProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<div>HOME-OUTLET</div>} />
          <Route path="inbox" element={<div>INBOX-OUTLET</div>} />
          <Route path="personal-inbox" element={<div>PERSONAL-OUTLET</div>} />
          <Route path="transactions" element={<div>TRANSACTIONS-OUTLET</div>} />
          <Route path="spending" element={<div>SPENDING-OUTLET</div>} />
          <Route path="exports" element={<div>EXPORTS-OUTLET</div>} />
          <Route path="settings" element={<div>SETTINGS-OUTLET</div>} />
        </Route>
      </Routes>
    </ThemeProvider>,
    { route },
  )
}

describe('AppShell navigation filter', () => {
  beforeEach(() => {
    useAppStore.setState({ user: { id: 1, username: 'u', display_name: 'User' }, authReady: true })
  })

  it('renders every nav link when no pages are hidden', async () => {
    server.use(
      http.get('/api/v1/settings', () => HttpResponse.json(DEFAULT_SETTINGS)),
    )
    mountAppShell('/')
    await screen.findByText('HOME-OUTLET')
    const desktopNav = screen.getByRole('navigation', { name: 'Primary' })
    expect(desktopNav).toHaveTextContent('Dashboard')
    expect(desktopNav).toHaveTextContent('Spending')
    expect(desktopNav).toHaveTextContent('Exports')
    expect(desktopNav).toHaveTextContent('Settings')
  })

  it('hides links present in hidden_pages from desktop + mobile nav', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({ ...DEFAULT_SETTINGS, hidden_pages: ['/spending', '/exports'] }),
      ),
    )
    mountAppShell('/')
    await screen.findByText('HOME-OUTLET')

    // Wait for settings to load before checking absence
    const desktopNav = await screen.findByRole('navigation', { name: 'Primary' })
    await waitFor(() => {
      expect(desktopNav).not.toHaveTextContent('Spending')
    })
    expect(desktopNav).not.toHaveTextContent('Exports')
    expect(desktopNav).toHaveTextContent('Dashboard')
    expect(desktopNav).toHaveTextContent('Settings')

    const mobileNav = screen.getByRole('navigation', { name: 'Primary mobile' })
    expect(mobileNav).not.toHaveTextContent('Spending')
    expect(mobileNav).not.toHaveTextContent('Exports')
    expect(mobileNav).toHaveTextContent('Dashboard')
  })

  it('keeps Settings visible even though it is not toggle-able', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({ ...DEFAULT_SETTINGS, hidden_pages: ['/'] }),
      ),
    )
    mountAppShell('/inbox')
    await screen.findByText('INBOX-OUTLET')
    const desktopNav = await screen.findByRole('navigation', { name: 'Primary' })
    await waitFor(() => {
      expect(desktopNav).not.toHaveTextContent('Dashboard')
    })
    expect(desktopNav).toHaveTextContent('Settings')
  })

  it('redirects from a hidden route to the first visible page', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({ ...DEFAULT_SETTINGS, hidden_pages: ['/spending'] }),
      ),
    )
    mountAppShell('/spending')
    // Initial render may show SPENDING-OUTLET before settings load; once
    // settings arrive, AppShell short-circuits to Navigate, and the index
    // route renders HOME-OUTLET.
    await screen.findByText('HOME-OUTLET')
    expect(screen.queryByText('SPENDING-OUTLET')).toBeNull()
  })

  it('falls back to the next visible page when Dashboard itself is hidden', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({ ...DEFAULT_SETTINGS, hidden_pages: ['/'] }),
      ),
    )
    mountAppShell('/')
    await screen.findByText('INBOX-OUTLET')
    expect(screen.queryByText('HOME-OUTLET')).toBeNull()
  })

  it('opens the command palette on Ctrl/⌘+K', async () => {
    server.use(http.get('/api/v1/settings', () => HttpResponse.json(DEFAULT_SETTINGS)))
    mountAppShell('/')
    await screen.findByText('HOME-OUTLET')

    expect(screen.queryByRole('dialog', { name: 'Command palette' })).toBeNull()
    fireEvent.keyDown(window, { key: 'k', metaKey: true })
    expect(await screen.findByRole('dialog', { name: 'Command palette' })).toBeInTheDocument()
  })

  it('opens the command palette from the sidebar search button', async () => {
    server.use(http.get('/api/v1/settings', () => HttpResponse.json(DEFAULT_SETTINGS)))
    mountAppShell('/')
    await screen.findByText('HOME-OUTLET')

    fireEvent.click(screen.getByRole('button', { name: /search/i }))
    expect(await screen.findByRole('dialog', { name: 'Command palette' })).toBeInTheDocument()
  })
})
