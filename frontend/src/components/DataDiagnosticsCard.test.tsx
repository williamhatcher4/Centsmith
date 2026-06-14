import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
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

afterEach(() => {
  // The desktop tests set window.__TAURI__; remove it so the browser-fallback
  // tests are not order-dependent on whether a desktop test ran first.
  delete window.__TAURI__
})

describe('DataDiagnosticsCard', () => {
  it('renders the data and diagnostics actions', () => {
    renderWithProviders(<DataDiagnosticsCard />)
    expect(screen.getByRole('button', { name: /back up data/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /restore from a file/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /open data folder/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /download support bundle/i })).not.toBeInTheDocument()
  })

  it('asks the backend to open the data folder', async () => {
    let opened = false
    server.use(
      http.post('/api/v1/maintenance/open-data-folder', () => {
        opened = true
        return HttpResponse.json({ opened: true, path: 'C:/Users/test/AppData/Roaming/Centsmith' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)
    await user.click(screen.getByRole('button', { name: /open data folder/i }))
    await waitFor(() => expect(opened).toBe(true))
  })

  it('shows the data folder path when the OS launcher is unavailable', async () => {
    server.use(
      http.post('/api/v1/maintenance/open-data-folder', () =>
        HttpResponse.json({ opened: false, path: 'C:/Users/test/AppData/Roaming/Centsmith' }),
      ),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)
    await user.click(screen.getByRole('button', { name: /open data folder/i }))
    expect(await screen.findByText(/Roaming\/Centsmith/i)).toBeInTheDocument()
  })

  it('writes a backup to disk via the backend in the desktop shell and shows the path', async () => {
    window.__TAURI__ = { core: { invoke: vi.fn() } }
    let calledToDisk = false
    server.use(
      http.post('/api/v1/maintenance/backup-to-disk', () => {
        calledToDisk = true
        return HttpResponse.json({ path: 'C:/Users/test/AppData/Roaming/Centsmith/backups/centsmith-backup-20260604-120000.db' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)

    await user.click(screen.getByRole('button', { name: /back up data/i }))

    await waitFor(() => expect(calledToDisk).toBe(true))
    expect(await screen.findByText(/Backup saved to .*centsmith-backup/i)).toBeInTheDocument()
  })

  it('the backup toast opens the backup folder, not the data folder', async () => {
    window.__TAURI__ = { core: { invoke: vi.fn() } }
    let openedBackupFolder = false
    let openedDataFolder = false
    server.use(
      http.post('/api/v1/maintenance/backup-to-disk', () =>
        HttpResponse.json({ path: 'D:/Backups/centsmith-backup-20260611-120000.db' }),
      ),
      http.post('/api/v1/maintenance/open-backup-folder', () => {
        openedBackupFolder = true
        return HttpResponse.json({ opened: true, path: 'D:/Backups' })
      }),
      http.post('/api/v1/maintenance/open-data-folder', () => {
        openedDataFolder = true
        return HttpResponse.json({ opened: true, path: 'C:/Users/test/AppData/Roaming/Centsmith' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)

    await user.click(screen.getByRole('button', { name: /back up data/i }))
    await user.click(await screen.findByRole('button', { name: /open folder/i }))

    await waitFor(() => expect(openedBackupFolder).toBe(true))
    expect(openedDataFolder).toBe(false)
  })

  it('downloads a backup in the browser build', async () => {
    let downloaded = false
    server.use(
      http.get('/api/v1/maintenance/backup', () => {
        downloaded = true
        return new HttpResponse(new Blob(['SQLite format 3 ']), {
          headers: { 'Content-Disposition': 'attachment; filename=centsmith-backup.db' },
        })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)

    await user.click(screen.getByRole('button', { name: /back up data/i }))

    await waitFor(() => expect(downloaded).toBe(true))
    expect(await screen.findByText(/Backup downloaded/i)).toBeInTheDocument()
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

  it('lists local backups and restores a chosen one after confirming', async () => {
    let restoredName: string | null = null
    server.use(
      http.get('/api/v1/maintenance/backups', () =>
        HttpResponse.json({
          backups: [
            { name: 'centsmith-backup-20260604-120000.db', size_bytes: 2_100_000, modified: '2026-06-04T12:00:00Z' },
          ],
        }),
      ),
      http.post('/api/v1/maintenance/restore-from-disk', async ({ request }) => {
        restoredName = ((await request.json()) as { name: string }).name
        return HttpResponse.json({ status: 'restored', message: 'Data restored.' })
      }),
    )
    const user = userEvent.setup()
    renderWithProviders(<DataDiagnosticsCard />)

    // The on-disk backup is listed without the user navigating the filesystem.
    expect(await screen.findByText('centsmith-backup-20260604-120000.db')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^restore$/i }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /^restore$/i }))

    await waitFor(() => expect(restoredName).toBe('centsmith-backup-20260604-120000.db'))
    expect(await screen.findByText(/Data restored/i)).toBeInTheDocument()
  })

  describe('backup folder setting', () => {
    it('shows the saved backup folder and disables Save while unchanged', async () => {
      server.use(
        http.get('/api/v1/settings', () =>
          HttpResponse.json({ personal_categories: ['Other'], hidden_pages: [], backup_folder: 'D:\\Backups' }),
        ),
      )
      renderWithProviders(<DataDiagnosticsCard />)
      await waitFor(() => expect((screen.getByLabelText('Backup folder') as HTMLInputElement).value).toBe('D:\\Backups'))
      expect(screen.getByRole('button', { name: /save folder/i })).toBeDisabled()
    })

    it('saves a new folder via the settings PUT and preserves categories/pages', async () => {
      let body: Record<string, unknown> | null = null
      server.use(
        http.get('/api/v1/settings', () =>
          HttpResponse.json({ personal_categories: ['Other', 'Income'], hidden_pages: ['/spending'], backup_folder: null }),
        ),
        http.put('/api/v1/settings', async ({ request }) => {
          body = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({ ...(body as object), backup_folder: 'E:\\CentsmithBackups' })
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<DataDiagnosticsCard />)

      const input = screen.getByLabelText('Backup folder')
      await user.type(input, 'E:\\CentsmithBackups')
      await user.click(screen.getByRole('button', { name: /save folder/i }))

      await waitFor(() => expect(body).not.toBeNull())
      expect(body).toEqual({
        personal_categories: ['Other', 'Income'],
        hidden_pages: ['/spending'],
        backup_folder: 'E:\\CentsmithBackups',
      })
      expect(await screen.findByText(/Backups will be saved to E:\\CentsmithBackups/i)).toBeInTheDocument()
    })

    it('clearing the input saves null to fall back to the default folder', async () => {
      let body: Record<string, unknown> | null = null
      server.use(
        http.get('/api/v1/settings', () =>
          HttpResponse.json({ personal_categories: ['Other'], hidden_pages: [], backup_folder: 'D:\\Backups' }),
        ),
        http.put('/api/v1/settings', async ({ request }) => {
          body = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({ ...(body as object), backup_folder: null })
        }),
      )
      const user = userEvent.setup()
      renderWithProviders(<DataDiagnosticsCard />)

      const input = screen.getByLabelText('Backup folder')
      await waitFor(() => expect((input as HTMLInputElement).value).toBe('D:\\Backups'))
      await user.clear(input)
      await user.click(screen.getByRole('button', { name: /save folder/i }))

      await waitFor(() => expect(body).not.toBeNull())
      expect(body).toMatchObject({ backup_folder: null })
      expect(await screen.findByText('Backups will use the default folder')).toBeInTheDocument()
    })

    it('surfaces a backend rejection of an invalid folder', async () => {
      server.use(
        http.get('/api/v1/settings', () =>
          HttpResponse.json({ personal_categories: ['Other'], hidden_pages: [], backup_folder: null }),
        ),
        http.put('/api/v1/settings', () =>
          HttpResponse.json({ detail: 'Backup folder does not exist or is not a directory.' }, { status: 400 }),
        ),
      )
      const user = userEvent.setup()
      renderWithProviders(<DataDiagnosticsCard />)

      await user.type(screen.getByLabelText('Backup folder'), 'Q:\\missing')
      await user.click(screen.getByRole('button', { name: /save folder/i }))

      expect(await screen.findByText(/does not exist/i)).toBeInTheDocument()
    })
  })
})
