import { useQuery } from '@tanstack/react-query'
import { settingsApi } from '../api/settings'
import type { TransactionType } from '../types'

export const SYSTEM_CATEGORIES = ['Income', 'Reimbursement', 'Transfer'] as const
export const INCOME_ONLY_CATEGORIES = ['Income', 'Reimbursement'] as const
const INCOME_ONLY_SET = new Set<string>(INCOME_ONLY_CATEGORIES)
const SYSTEM_SET = new Set<string>(SYSTEM_CATEGORIES)

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
  const incomeOnly = all.filter((c) => INCOME_ONLY_SET.has(c))
  const spending = all.filter((c) => !INCOME_ONLY_SET.has(c))
  const credit = [...incomeOnly, ...spending]

  return {
    all,
    spending,
    credit,
    isLoading,
    isSystem: (name: string) => SYSTEM_SET.has(name),
    categoriesFor: (tx) => (tx.transaction_type === 'credit' ? credit : spending),
  }
}
