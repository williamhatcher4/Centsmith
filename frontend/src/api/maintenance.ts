import type { LocalBackup } from '../types'

interface TauriGlobal {
  core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
}

declare global {
  interface Window {
    __TAURI__?: TauriGlobal
  }
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null)
  return (body && typeof body.detail === 'string' && body.detail) || fallback
}

/** True inside the desktop shell (Tauri injects this global on every page). */
function isDesktop(): boolean {
  return !!window.__TAURI__
}

/** Browser download via a synthetic `<a download>` (used in the web build). */
async function browserDownload(path: string, fallback: string): Promise<void> {
  const res = await fetch(path, { credentials: 'include' })
  if (!res.ok) throw new Error(await errorMessage(res, fallback))
  const disposition = res.headers.get('Content-Disposition') ?? ''
  const match = disposition.match(/filename=([^;]+)/)
  const filename = match ? match[1].trim() : path.split('/').pop() ?? 'download'
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export const maintenanceApi = {
  /**
   * Back up the database. In the desktop shell, WebView2 ignores `<a download>`
   * blob clicks and the webview's remote-origin Tauri IPC is unreliable, so the
   * local backend writes the file next to the database and returns its path. In
   * the browser, do a normal download. `path` is set only for the desktop case.
   */
  downloadBackup: async (): Promise<{ path?: string }> => {
    if (isDesktop()) {
      const res = await fetch('/api/v1/maintenance/backup-to-disk', { method: 'POST', credentials: 'include' })
      if (!res.ok) throw new Error(await errorMessage(res, 'Backup failed'))
      return { path: (await res.json()).path as string }
    }
    await browserDownload('/api/v1/maintenance/backup', 'Backup failed')
    return {}
  },
  restore: async (file: File): Promise<{ message: string }> => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/v1/maintenance/restore', { method: 'POST', credentials: 'include', body })
    if (!res.ok) throw new Error(await errorMessage(res, 'Restore failed'))
    return res.json()
  },
  /** Backups saved on disk (newest first), for one-click in-app restore. */
  listBackups: async (): Promise<LocalBackup[]> => {
    const res = await fetch('/api/v1/maintenance/backups', { credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not list backups'))
    return (await res.json()).backups as LocalBackup[]
  },
  /** Restore one of the on-disk backups by filename (no upload needed). */
  restoreFromDisk: async (name: string): Promise<{ message: string }> => {
    const res = await fetch('/api/v1/maintenance/restore-from-disk', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) throw new Error(await errorMessage(res, 'Restore failed'))
    return res.json()
  },
  /**
   * Ask the local backend to reveal the data folder in the OS file manager.
   * The backend runs on the same machine as the desktop shell, so this works
   * without relying on the webview's remote-origin Tauri IPC. Returns
   * `opened: false` plus the path when the launcher is unavailable so the caller
   * can display it instead.
   */
  openDataFolder: async (): Promise<{ opened: boolean; path: string }> => {
    const res = await fetch('/api/v1/maintenance/open-data-folder', { method: 'POST', credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not open the data folder'))
    return (await res.json()) as { opened: boolean; path: string }
  },
  /**
   * Reveal the folder backups are written to — the configured backup folder
   * when one is set, else `backups/` beside the database. Not the same folder
   * as `openDataFolder` once a custom backup folder is configured.
   */
  openBackupFolder: async (): Promise<{ opened: boolean; path: string }> => {
    const res = await fetch('/api/v1/maintenance/open-backup-folder', { method: 'POST', credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not open the backup folder'))
    return (await res.json()) as { opened: boolean; path: string }
  },
}
