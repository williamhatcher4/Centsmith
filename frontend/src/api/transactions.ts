import { api } from './client'
import type { Classification, ClassificationFilter, ColumnMapping, DashboardSummary, ExpensedFilter, ImportPreview, ImportResult, SpendingSummary, Transaction, TransactionCreatePayload, TransactionPage } from '../types'

export interface ImportOptions {
  chargesPositive?: boolean
  mapping?: ColumnMapping
  profileId?: number
  cardId?: number
}

function importFormData(file: File, options: ImportOptions = {}): FormData {
  const body = new FormData()
  body.append('file', file)
  if (options.chargesPositive !== undefined) body.append('charges_positive', String(options.chargesPositive))
  if (options.mapping) body.append('column_mapping', JSON.stringify(options.mapping))
  if (options.profileId !== undefined) body.append('profile_id', String(options.profileId))
  if (options.cardId !== undefined) body.append('card_id', String(options.cardId))
  return body
}

export interface TransactionFilters {
  classification?: ClassificationFilter
  personal_category?: string
  expensed?: ExpensedFilter
  card_id?: number
  start_date?: string
  end_date?: string
  limit?: number
  skip?: number
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
  list: (filters: TransactionFilters = {}) => api.get<TransactionPage>(`/api/v1/transactions${qs(filters)}`),
  update: (id: number, data: Partial<Pick<Transaction, 'classification' | 'personal_category' | 'description' | 'transaction_date' | 'expensed' | 'card_id'>>) => api.put<Transaction>(`/api/v1/transactions/${id}`, data),
  bulkAssignCard: (transactionIds: number[], cardId: number | null) =>
    api.post<{ updated: number }>('/api/v1/transactions/bulk-assign-card', { transaction_ids: transactionIds, card_id: cardId }),
  createManual: (data: TransactionCreatePayload) => api.post<Transaction>('/api/v1/transactions/manual', data),
  deleteTransaction: (id: number) => api.delete<Transaction>(`/api/v1/transactions/${id}`),
  bulkClassify: (transactionIds: number[], classification: Classification) => api.post<{ updated: number }>('/api/v1/transactions/bulk-classify', { transaction_ids: transactionIds, classification }),
  bulkCategorizePersonal: (transactionIds: number[], personalCategory: string) =>
    api.post<{ updated: number }>('/api/v1/transactions/bulk-categorize-personal', {
      transaction_ids: transactionIds,
      personal_category: personalCategory,
    }),
  dashboard: (months = 12) => api.get<DashboardSummary>(`/api/v1/transactions/dashboard?months=${months}`),
  personalSpending: (months = 12) => api.get<SpendingSummary>(`/api/v1/transactions/spending/personal?months=${months}`),
  personalIncome: (months = 12) => api.get<SpendingSummary>(`/api/v1/transactions/income/personal?months=${months}`),
  previewImport: async (file: File, options: ImportOptions = {}): Promise<ImportPreview> => {
    const res = await fetch('/api/v1/transactions/import/preview', { method: 'POST', credentials: 'include', body: importFormData(file, options) })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Preview failed')
    return res.json()
  },
  confirmImport: async (file: File, options: ImportOptions = {}): Promise<ImportResult> => {
    const res = await fetch('/api/v1/transactions/import/confirm', { method: 'POST', credentials: 'include', body: importFormData(file, options) })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Import failed')
    return res.json()
  },
  previewCheckingImport: async (file: File, options: ImportOptions = {}): Promise<ImportPreview> => {
    const res = await fetch('/api/v1/transactions/import/checking/preview', { method: 'POST', credentials: 'include', body: importFormData(file, options) })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Preview failed')
    return res.json()
  },
  confirmCheckingImport: async (file: File, options: ImportOptions = {}): Promise<ImportResult> => {
    const res = await fetch('/api/v1/transactions/import/checking/confirm', { method: 'POST', credentials: 'include', body: importFormData(file, options) })
    if (!res.ok) throw new Error((await res.json()).detail ?? 'Import failed')
    return res.json()
  },
}

