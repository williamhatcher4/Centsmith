import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { LicenseUpdatesCard } from './LicenseUpdatesCard'

// The card renders only inside the desktop shell, gated on the `__TAURI__`
// global. License read/write goes through the local backend
// (`/api/v1/maintenance/license`), not Tauri IPC, so these tests drive MSW.
beforeEach(() => {
  window.__TAURI__ = { core: { invoke: () => Promise.resolve() } }
})

afterEach(() => {
  delete window.__TAURI__
})

describe('LicenseUpdatesCard', () => {
  it('shows the disabled state when no license is stored', async () => {
    renderWithProviders(<LicenseUpdatesCard />)
    expect(await screen.findByText(/no license entered/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })

  it('saves a pasted license and reflects the active status', async () => {
    let sentToken: string | null = null
    server.use(
      http.post('/api/v1/maintenance/license', async ({ request }) => {
        sentToken = ((await request.json()) as { token: string }).token
        return HttpResponse.json({ present: true, hint: '…WXYZ' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<LicenseUpdatesCard />)
    await screen.findByText(/no license entered/i)

    await user.type(screen.getByLabelText(/license key/i), 'my-key-WXYZ')
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByText(/active license ending/i)).toBeInTheDocument()
    expect(screen.getByText('…WXYZ')).toBeInTheDocument()
    expect(sentToken).toBe('my-key-WXYZ')
  })

  it('does not call the backend when saving with an empty field', async () => {
    let called = false
    server.use(
      http.post('/api/v1/maintenance/license', () => {
        called = true
        return HttpResponse.json({ present: false, hint: null })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<LicenseUpdatesCard />)
    await screen.findByText(/no license entered/i)

    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByText(/paste your license key first/i)).toBeInTheDocument()
    expect(called).toBe(false)
  })

  it('removes a stored license', async () => {
    let cleared = false
    server.use(
      http.get('/api/v1/maintenance/license', () => HttpResponse.json({ present: true, hint: '…WXYZ' })),
      http.delete('/api/v1/maintenance/license', () => {
        cleared = true
        return HttpResponse.json({ present: false, hint: null })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<LicenseUpdatesCard />)
    expect(await screen.findByText(/active license ending/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /remove/i }))

    expect(await screen.findByText(/no license entered/i)).toBeInTheDocument()
    expect(cleared).toBe(true)
  })

  it('surfaces a backend error when reading status fails', async () => {
    server.use(
      http.get('/api/v1/maintenance/license', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
    )
    renderWithProviders(<LicenseUpdatesCard />)
    // Read failures fall back to the no-license state (the card still renders).
    expect(await screen.findByText(/no license entered/i)).toBeInTheDocument()
  })

  it('shows that no update check has run yet', async () => {
    renderWithProviders(<LicenseUpdatesCard />)
    expect(await screen.findByText(/no update check has run yet/i)).toBeInTheDocument()
  })

  it('shows a successful update check with a relative timestamp', async () => {
    server.use(
      http.get('/api/v1/maintenance/update-status', () =>
        HttpResponse.json({
          present: true,
          checked_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
          result: 'ok-uptodate',
          detail: '',
        }),
      ),
    )
    renderWithProviders(<LicenseUpdatesCard />)
    expect(
      await screen.findByText(/last update check: 5 minutes ago — up to date/i),
    ).toBeInTheDocument()
  })

  it('shows a failed update check with its detail', async () => {
    server.use(
      http.get('/api/v1/maintenance/update-status', () =>
        HttpResponse.json({
          present: true,
          checked_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
          result: 'error',
          detail: 'could not reach update server',
        }),
      ),
    )
    renderWithProviders(<LicenseUpdatesCard />)
    expect(
      await screen.findByText(/last update check: 1 hour ago — failed: could not reach update server/i),
    ).toBeInTheDocument()
  })

  it('shows a skipped check when no license is stored', async () => {
    server.use(
      http.get('/api/v1/maintenance/update-status', () =>
        HttpResponse.json({
          present: true,
          checked_at: new Date().toISOString(),
          result: 'skipped-no-license',
          detail: 'No license stored; update checks are disabled.',
        }),
      ),
    )
    renderWithProviders(<LicenseUpdatesCard />)
    expect(
      await screen.findByText(/last update check: just now — skipped \(no license\)/i),
    ).toBeInTheDocument()
  })

  it('hides the update-check line when the status read fails', async () => {
    server.use(
      http.get('/api/v1/maintenance/update-status', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderWithProviders(<LicenseUpdatesCard />)
    await screen.findByText(/no license entered/i)
    expect(screen.queryByText(/last update check/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/no update check has run yet/i)).not.toBeInTheDocument()
  })
})
