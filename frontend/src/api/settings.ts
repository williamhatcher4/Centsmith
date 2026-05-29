import { api } from './client'
import type { UserSettings } from '../types'

export interface UpdateSettingsOptions {
  on_delete?: 'reject' | 'relabel'
  relabel_target?: string
}

function buildQuery(opts: UpdateSettingsOptions | undefined): string {
  if (!opts) return ''
  const params = new URLSearchParams()
  if (opts.on_delete) params.set('on_delete', opts.on_delete)
  if (opts.relabel_target) params.set('relabel_target', opts.relabel_target)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export const settingsApi = {
  get: () => api.get<UserSettings>('/api/v1/settings'),
  update: (payload: UserSettings, opts?: UpdateSettingsOptions) =>
    api.put<UserSettings>(`/api/v1/settings${buildQuery(opts)}`, payload),
  getCategoryUsage: () => api.get<Record<string, number>>('/api/v1/settings/category-usage'),
}
