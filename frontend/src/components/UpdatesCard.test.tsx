import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { UpdatesCard } from './UpdatesCard'

// The card renders only inside the desktop shell, gated on the `__TAURI__`
// global. Update status is read from the local backend, so these tests drive MSW.
beforeEach(() => {
  window.__TAURI__ = { core: { invoke: () => Promise.resolve() } }
})

afterEach(() => {
  delete window.__TAURI__
})

describe('UpdatesCard', () => {
  it('says updates are free and has no license field', async () => {
    renderWithProviders(<UpdatesCard />)
    expect(await screen.findByText(/centsmith is free/i)).toBeInTheDocument()
    expect(screen.queryByLabelText(/license/i)).not.toBeInTheDocument()
  })

  it('shows that no update check has run yet', async () => {
    renderWithProviders(<UpdatesCard />)
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
    renderWithProviders(<UpdatesCard />)
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
    renderWithProviders(<UpdatesCard />)
    expect(
      await screen.findByText(/last update check: 1 hour ago — failed: could not reach update server/i),
    ).toBeInTheDocument()
  })

  it('hides the update-check line when the status read fails', async () => {
    server.use(
      http.get('/api/v1/maintenance/update-status', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    renderWithProviders(<UpdatesCard />)
    await screen.findByText(/centsmith is free/i)
    expect(screen.queryByText(/last update check/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/no update check has run yet/i)).not.toBeInTheDocument()
  })
})
