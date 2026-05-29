import { api } from './client'
import type { ImportBatch, ImportBatchDeleteResult } from '../types'

export const importsApi = {
  list: () => api.get<ImportBatch[]>('/api/v1/imports'),
  deleteBatch: (id: string) => api.delete<ImportBatchDeleteResult>(`/api/v1/imports/${id}`),
}
