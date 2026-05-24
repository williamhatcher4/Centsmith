export type Classification = 'personal' | 'work'
export type ClassificationFilter = Classification | 'unsorted' | 'all'
export type ExpensedFilter = 'all' | 'expensed' | 'unexpensed'
export type TransactionType = 'debit' | 'credit'

export interface User {
  id: number
  username: string
  display_name: string
}

export interface Transaction {
  id: number
  transaction_date: string
  description: string
  amount_cents: number
  transaction_type: TransactionType
  classification: Classification | null
  personal_category: string | null
  expensed: boolean
  statement_format: string | null
  imported_at: string
}

export interface ImportPreviewRow {
  row_number: number
  date: string
  description: string
  amount_cents: number
  transaction_type: TransactionType
  is_duplicate: boolean
}

export interface ImportPreview {
  rows: ImportPreviewRow[]
  total: number
  duplicates: number
  ignored_credits: number
  to_import: number
  statement_format: string
}

export interface ImportResult {
  imported: number
  skipped: number
  ignored_credits: number
}

export interface SpendingSummary {
  total_cents: number
  average_per_month_cents: number
  points: SpendingPoint[]
  by_category: SpendingByCategory[]
}

export interface SpendingByCategory {
  category_name: string
  amount_cents: number
  percent: number
}

export interface SpendingPoint {
  label: string
  amount_cents: number
  by_category: SpendingByCategory[]
}

export interface DashboardMonth {
  month: string
  personal_cents: number
  work_cents: number
  income_cents: number
  reimbursement_cents: number
}

export interface DashboardSummary {
  personal_total_cents: number
  work_total_cents: number
  unsorted_count: number
  latest_month: string | null
  months: DashboardMonth[]
  income_total_cents: number
  reimbursement_total_cents: number
  uncategorized_income_cents: number
  uncategorized_income_count: number
}
