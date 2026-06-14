import { useQuery } from '@tanstack/react-query'
import { settingsApi } from '../api/settings'
import type { TransactionType } from '../types'

// Fallbacks while /settings is loading (or for older backends that don't send
// the rule fields). The server response is the source of truth.
export const SYSTEM_CATEGORIES = ['Income', 'Reimbursement', 'Transfer'] as const
export const INCOME_ONLY_CATEGORIES = ['Income', 'Reimbursement'] as const

const FALLBACK_CATEGORIES = [
  'Groceries', 'Dining', 'Transportation', 'Home', 'Health',
  'Subscriptions', 'Shopping', 'Travel', 'Entertainment',
  'Personal Care', 'Gifts', 'Other', 'Transfer', 'Income', 'Reimbursement',
]

export interface UseCategoriesResult {
  all: string[]
  spending: string[]
  credit: string[]
  isLoading: boolean
  isSystem: (name: string) => boolean
  categoriesFor: (tx: { transaction_type: TransactionType }) => string[]
}

export function useCategories(): UseCategoriesResult {
  const { data, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.get(),
    staleTime: 60_000,
  })

  const all = data?.personal_categories ?? FALLBACK_CATEGORIES
  const incomeOnlySet = new Set<string>(data?.credit_only_categories ?? INCOME_ONLY_CATEGORIES)
  const systemSet = new Set<string>(data?.system_categories ?? SYSTEM_CATEGORIES)
  const incomeOnly = all.filter((c) => incomeOnlySet.has(c))
  const spending = all.filter((c) => !incomeOnlySet.has(c))
  const credit = [...incomeOnly, ...spending]

  return {
    all,
    spending,
    credit,
    isLoading,
    isSystem: (name: string) => systemSet.has(name),
    categoriesFor: (tx) => (tx.transaction_type === 'credit' ? credit : spending),
  }
}
