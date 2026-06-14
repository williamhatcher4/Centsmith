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
  is_manual: boolean
  statement_format: string | null
  card_id: number | null
  imported_at: string
}

export interface Card {
  id: number
  name: string
  last4: string | null
  statement_day: number | null
}

export interface CardPayload {
  name: string
  last4?: string | null
  statement_day?: number | null
}

export interface StatementSummary {
  card_id: number
  start_date: string
  end_date: string
  charges_cents: number
  payments_cents: number
  net_cents: number
  charge_count: number
  payment_count: number
}

export interface TransactionPage {
  items: Transaction[]
  total: number
  skip: number
  limit: number
  has_more: boolean
  next_skip: number | null
}

export interface TransactionCreatePayload {
  transaction_date: string
  description: string
  amount_cents: number
  transaction_type: TransactionType
  classification?: Classification | null
  personal_category?: string | null
  expensed?: boolean
}

export interface ImportPreviewRow {
  row_number: number
  date: string
  description: string
  amount_cents: number
  transaction_type: TransactionType
  is_duplicate: boolean
  is_ignored_credit: boolean
}

export interface SkippedRow {
  row_number: number
  raw_date: string
  raw_amount: string
  raw_description: string
  reason_code: string
  message: string
}

export interface ImportPreview {
  rows: ImportPreviewRow[]
  total: number
  duplicates: number
  ignored_credits: number
  to_import: number
  statement_format: string
  skipped_errors: number
  amount_sign_adjustable: boolean
  charges_positive: boolean
  date_convention_adjustable: boolean
  day_first: boolean
  skipped_rows: SkippedRow[]
  mapping_required: boolean
  available_columns: string[]
  sample_rows: string[][]
  detected_columns: Record<string, number | null>
}

export type AmountConvention = 'signed' | 'charges_positive' | 'charges_negative'
export type DateConvention = 'mdy' | 'dmy'

export interface ColumnMapping {
  date_column: number
  description_column: number
  amount_column?: number | null
  debit_column?: number | null
  credit_column?: number | null
  amount_convention: AmountConvention
  date_convention?: DateConvention | null
}

export interface ImportProfile {
  id: number
  name: string
  source_type: 'card' | 'checking'
  date_column: number
  description_column: number
  amount_column: number | null
  debit_column: number | null
  credit_column: number | null
  amount_convention: AmountConvention
  date_convention: DateConvention | null
  ignored_payment_patterns: string[]
  created_at: string
  updated_at: string
}

export interface ImportProfilePayload {
  name: string
  source_type: 'card' | 'checking'
  date_column: number
  description_column: number
  amount_column?: number | null
  debit_column?: number | null
  credit_column?: number | null
  amount_convention: AmountConvention
  date_convention?: DateConvention | null
  ignored_payment_patterns: string[]
}

export interface ImportResult {
  imported: number
  skipped: number
  ignored_credits: number
  skipped_errors: number
  batch_id: string | null
}

export interface ImportBatch {
  id: string
  filename: string
  statement_format: string | null
  imported_at: string
  row_count: number
  created_by_action: string
}

export interface ImportBatchDeleteResult {
  removed_rows: number
  classified_rows: number
  categorized_rows: number
}

export interface LocalBackup {
  name: string
  size_bytes: number
  modified: string
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

export interface UserSettings {
  personal_categories: string[]
  hidden_pages: string[]
  // Optional custom backup destination; null means the default backups/
  // folder beside the database. Omitting it from a PUT leaves it unchanged.
  backup_folder?: string | null
  // Business-rule constants served by the backend (read-only; optional so PUT
  // payloads and older mocks don't need to carry them).
  system_categories?: string[]
  credit_only_categories?: string[]
}

export interface MerchantSpend {
  name: string
  amount_cents: number
  count: number
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
  unexpensed_work_cents: number
  unexpensed_work_count: number
  top_merchants: MerchantSpend[]
}
