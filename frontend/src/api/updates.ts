interface TauriGlobal {
  core?: { invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
}

declare global {
  interface Window {
    __TAURI__?: TauriGlobal
  }
}

/**
 * Outcome of the last auto-update check, recorded by the Rust shell into
 * `update-check.json` beside the database and served by the local backend.
 * `present` is false until the shell has attempted at least one check.
 */
export interface UpdateCheckStatus {
  present: boolean
  checked_at: string | null
  result: 'ok-uptodate' | 'ok-update-available' | 'error' | null
  detail: string | null
}

/**
 * True only inside the desktop shell, where auto-update is relevant. The
 * `__TAURI__` global is reliably injected on every page (`withGlobalTauri`), so
 * it's a safe render gate.
 */
export function isDesktop(): boolean {
  return !!window.__TAURI__
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null)
  return (body && typeof body.detail === 'string' && body.detail) || fallback
}

/** Read-only view of the desktop shell's automatic update checks. */
export const updatesApi = {
  isDesktop,
  getUpdateStatus: async (): Promise<UpdateCheckStatus> => {
    const res = await fetch('/api/v1/maintenance/update-status', { credentials: 'include' })
    if (!res.ok) throw new Error(await errorMessage(res, 'Could not read update status'))
    return (await res.json()) as UpdateCheckStatus
  },
}
