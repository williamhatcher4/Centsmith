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

function tauriInvoke() {
  return window.__TAURI__?.core?.invoke
}

/** True only inside the desktop shell, where the license commands exist. */
export function isDesktop(): boolean {
  return !!tauriInvoke()
}

/**
 * Manage the update license token that gates auto-update. The token lives on
 * the Rust side (a file the updater reads); these are thin Tauri-command
 * bridges. Licensing is desktop-only, so the web build never sees this UI.
 */
export const licenseApi = {
  isDesktop,
  getStatus: async (): Promise<LicenseStatus> => {
    const invoke = tauriInvoke()
    if (!invoke) return { present: false, hint: null }
    return (await invoke('get_license_status')) as LicenseStatus
  },
  set: async (token: string): Promise<LicenseStatus> => {
    const invoke = tauriInvoke()
    if (!invoke) throw new Error('License management is only available in the desktop app.')
    return (await invoke('set_license_token', { token })) as LicenseStatus
  },
  clear: async (): Promise<LicenseStatus> => {
    const invoke = tauriInvoke()
    if (!invoke) throw new Error('License management is only available in the desktop app.')
    return (await invoke('clear_license_token')) as LicenseStatus
  },
}
