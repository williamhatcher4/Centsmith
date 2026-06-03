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

/** Trigger a browser download of a blob from a maintenance endpoint. */
async function downloadFrom(path: string, fallback: string): Promise<void> {
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
  downloadBackup: () => downloadFrom('/api/v1/maintenance/backup', 'Backup failed'),
  downloadSupportBundle: () => downloadFrom('/api/v1/maintenance/support-bundle', 'Could not build support bundle'),
  restore: async (file: File): Promise<{ message: string }> => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/v1/maintenance/restore', { method: 'POST', credentials: 'include', body })
    if (!res.ok) throw new Error(await errorMessage(res, 'Restore failed'))
    return res.json()
  },
  dataLocation: async (): Promise<string> => {
    const res = await fetch('/api/v1/maintenance/data-location', { credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not resolve the data folder'))
    return (await res.json()).path
  },
  /**
   * Open the OS data folder via the Tauri command when running in the desktop
   * shell; otherwise resolve the path so the caller can display it.
   */
  openDataFolder: async (): Promise<{ opened: boolean; path: string }> => {
    const invoke = window.__TAURI__?.core?.invoke
    if (invoke) {
      const path = (await invoke('open_data_folder')) as string
      return { opened: true, path }
    }
    const path = await maintenanceApi.dataLocation()
    return { opened: false, path }
  },
}
