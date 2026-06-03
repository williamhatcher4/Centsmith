import { api } from './client'
import type { ImportProfile, ImportProfilePayload } from '../types'

export const importProfilesApi = {
  list: () => api.get<ImportProfile[]>('/api/v1/import-profiles'),
  create: (payload: ImportProfilePayload) => api.post<ImportProfile>('/api/v1/import-profiles', payload),
  update: (id: number, payload: ImportProfilePayload) => api.put<ImportProfile>(`/api/v1/import-profiles/${id}`, payload),
  remove: (id: number) => api.delete<void>(`/api/v1/import-profiles/${id}`),
}
