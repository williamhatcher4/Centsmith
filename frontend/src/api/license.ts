interface TauriGlobal {
  core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
}

declare global {
  interface Window {
    __TAURI__?: TauriGlobal
  }
}

export interface LicenseStatus {
  present: boolean
  hint: string | null
}

/**
 * Outcome of the last auto-update check, recorded by the Rust shell into
 * `update-check.json` beside the database and served by the local backend.
 * `present` is false until the shell has attempted at least one check.
 */
export interface UpdateCheckStatus {
  present: boolean
  checked_at: string | null
  result: 'ok-uptodate' | 'ok-update-available' | 'skipped-no-license' | 'error' | null
  detail: string | null
}

/**
 * True only inside the desktop shell, where auto-update (and therefore the
 * license) is relevant. The `__TAURI__` global is reliably injected on every
 * page (`withGlobalTauri`), so it's a safe render gate — but the license
 * *operations* go through the local backend below, not Tauri IPC, because the
 * webview's remote-origin IPC invoke is unreliable for the backend-served page
 * (same reason backup / open-data-folder moved to the backend).
 */
export function isDesktop(): boolean {
  return !!window.__TAURI__
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null)
  return (body && typeof body.detail === 'string' && body.detail) || fallback
}

/**
 * Manage the update license token that gates auto-update. The token is stored by
 * the local backend in the data dir (the same `license.token` file the Tauri
 * updater reads as a bearer header); these are thin REST bridges. Licensing is
 * desktop-only, so the card is only rendered when `isDesktop()`.
 */
export const licenseApi = {
  isDesktop,
  getStatus: async (): Promise<LicenseStatus> => {
    const res = await fetch('/api/v1/maintenance/license', { credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not read license status'))
    return (await res.json()) as LicenseStatus
  },
  set: async (token: string): Promise<LicenseStatus> => {
    const res = await fetch('/api/v1/maintenance/license', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not save license'))
    return (await res.json()) as LicenseStatus
  },
  clear: async (): Promise<LicenseStatus> => {
    const res = await fetch('/api/v1/maintenance/license', { method: 'DELETE', credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not remove license'))
    return (await res.json()) as LicenseStatus
  },
  getUpdateStatus: async (): Promise<UpdateCheckStatus> => {
    const res = await fetch('/api/v1/maintenance/update-status', { credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not read update status'))
    return (await res.json()) as UpdateCheckStatus
  },
}
