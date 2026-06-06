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
})
