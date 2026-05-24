import { api } from './client'
import type { Classification, ClassificationFilter, DashboardSummary, ExpensedFilter, ImportPreview, ImportResult, SpendingSummary, Transaction } from '../types'

export interface TransactionFilters {
  classification?: ClassificationFilter
  personal_category?: 'uncategorized'
  expensed?: ExpensedFilter
  start_date?: string
  end_date?: string
  limit?: number
}

function qs(filters: TransactionFilters) {
  const params = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== '' && value !== 'all') {
      params.set(key, value === 'expensed' ? 'true' : value === 'unexpensed' ? 'false' : String(value))
    }
  })
  const text = params.toString()
  return text ? `?${text}` : ''
}

export const transactionsApi = {
  list: (filters: TransactionFilters = {}) => api.get<Transaction[]>(`/api/v1/transactions${qs(filters)}`),
  update: (id: number, data: Partial<Pick<Transaction, 'classification' | 'personal_category' | 'description' | 'transaction_date' | 'expensed'>>) => api.put<Transaction>(`/api/v1/transactions/${id}`, data),
  bulkClassify: (transactionIds: number[], classification: Classification) => api.post<{ updated: number }>('/api/v1/transactions/bulk-classify', { transaction_ids: transactionIds, classification }),
  bulkCategorizePersonal: (transactionIds: number[], personalCategory: string) =>
    api.post<{ updated: number }>('/api/v1/transactions/bulk-categorize-personal', {
      transaction_ids: transactionIds,
      personal_category: personalCategory,
    }),
  dashboard: () => api.get<DashboardSummary>('/api/v1/transactions/dashboard'),
  personalSpending: (months = 12) => api.get<SpendingSummary>(`/api/v1/transactions/spending/personal?months=${months}`),
  personalIncome: (months = 12) => api.get<SpendingSummary>(`/api/v1/transactions/income/personal?months=${months}`),
  previewImport: async (file: File): Promise<ImportPreview> => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/v1/transactions/import/preview', { method: 'POST', credentials: 'include', body })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Preview failed')
    return res.json()
  },
  confirmImport: async (file: File): Promise<ImportResult> => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/v1/transactions/import/confirm', { method: 'POST', credentials: 'include', body })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Import failed')
    return res.json()
  },
  previewCheckingImport: async (file: File): Promise<ImportPreview> => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/v1/transactions/import/checking/preview', { method: 'POST', credentials: 'include', body })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Preview failed')
    return res.json()
  },
  confirmCheckingImport: async (file: File): Promise<ImportResult> => {
    const body = new FormData()
    body.append('file', file)
    const res = await fetch('/api/v1/transactions/import/checking/confirm', { method: 'POST', credentials: 'include', body })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Import failed')
    return res.json()
  },
}

