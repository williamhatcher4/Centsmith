import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { DataDiagnosticsCard } from './DataDiagnosticsCard'

beforeEach(() => {
  // jsdom lacks object-URL plumbing used by the download helper.
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:mock')
  globalThis.URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

describe('DataDiagnosticsCard', () => {
  it('renders the data and diagnostics actions', () => {
    renderWithProviders(<DataDiagnosticsCard />)
    expect(screen.getByRole('button', { name: /back up data/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /restore from backup/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open data folder/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /download support bundle/i })).toBeInTheDocument()
  })

  it('shows the data folder path when not running in the desktop shell', async () => {
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)
    await user.click(screen.getByRole('button', { name: /open data folder/i }))
    expect(await screen.findByText(/Roaming\/Centsmith/i)).toBeInTheDocument()
  })

  it('confirms before restoring and posts the chosen file', async () => {
    let restoreCalled = false
    server.use(
      http.post('/api/v1/maintenance/restore', () => {
        restoreCalled = true
        return HttpResponse.json({ status: 'restored', message: 'Data restored.' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)

    const file = new File([new Uint8Array([1, 2, 3])], 'backup.db', { type: 'application/x-sqlite3' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    // Destructive confirm dialog appears first.
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: /^restore$/i }))

    await waitFor(() => expect(restoreCalled).toBe(true))
    expect(await screen.findByText(/Data restored/i)).toBeInTheDocument()
  })

  it('does not restore when the confirm dialog is cancelled', async () => {
    let restoreCalled = false
    server.use(
      http.post('/api/v1/maintenance/restore', () => {
        restoreCalled = true
        return HttpResponse.json({ status: 'restored', message: 'Data restored.' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)

    const file = new File([new Uint8Array([1, 2, 3])], 'backup.db', { type: 'application/x-sqlite3' })
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    await user.upload(input, file)

    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(restoreCalled).toBe(false)
  })
})
