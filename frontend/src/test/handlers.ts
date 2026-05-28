import { http, HttpResponse } from 'msw'
import type { DashboardSummary, ImportBatch, SpendingSummary, Transaction, User, UserSettings } from '../types'

export const mockUser: User = {
  id: 1,
  username: 'user1',
  display_name: 'User 1',
}

export const mockTransactions: Transaction[] = [
  {
    id: 1,
    transaction_date: '2026-05-01',
    description: 'Coffee shop',
    amount_cents: 425,
    transaction_type: 'debit',
    classification: null,
    personal_category: null,
    expensed: false,
    is_manual: false,
    statement_format: 'test',
    imported_at: '2026-05-01T12:00:00Z',
  },
  {
    id: 2,
    transaction_date: '2026-05-02',
    description: 'Grocery store',
    amount_cents: 4250,
    transaction_type: 'debit',
    classification: null,
    personal_category: null,
    expensed: false,
    is_manual: false,
    statement_format: 'test',
    imported_at: '2026-05-02T12:00:00Z',
  },
]

export const mockManualTransaction: Transaction = {
  id: 99,
  transaction_date: '2026-05-10',
  description: 'Manual entry',
  amount_cents: 1500,
  transaction_type: 'debit',
  classification: null,
  personal_category: null,
  expensed: false,
  is_manual: true,
  statement_format: null,
  imported_at: '2026-05-10T12:00:00Z',
}

export const mockDashboard: DashboardSummary = {
  personal_total_cents: 50000,
  work_total_cents: 12500,
  unsorted_count: 2,
  latest_month: '2026-05',
  months: [
    { month: '2026-04', personal_cents: 30000, work_cents: 5000, income_cents: 0, reimbursement_cents: 0 },
    { month: '2026-05', personal_cents: 20000, work_cents: 7500, income_cents: 200000, reimbursement_cents: 0 },
  ],
  income_total_cents: 200000,
  reimbursement_total_cents: 0,
  uncategorized_income_cents: 0,
  uncategorized_income_count: 0,
}

export const mockSpending: SpendingSummary = {
  total_cents: 50000,
  average_per_month_cents: 25000,
  points: [
    { label: '2026-04', amount_cents: 30000, by_category: [{ category_name: 'Dining', amount_cents: 30000, percent: 100 }] },
    { label: '2026-05', amount_cents: 20000, by_category: [{ category_name: 'Dining', amount_cents: 20000, percent: 100 }] },
  ],
  by_category: [{ category_name: 'Dining', amount_cents: 50000, percent: 100 }],
}

export const mockImportBatches: ImportBatch[] = [
  {
    id: 'batch-1',
    filename: 'may-statement.csv',
    statement_format: 'Account Activity CSV',
    imported_at: '2026-05-15T12:00:00Z',
    row_count: 12,
    created_by_action: 'import',
  },
  {
    id: 'batch-2',
    filename: 'april-statement.csv',
    statement_format: 'Account Activity CSV',
    imported_at: '2026-04-10T10:00:00Z',
    row_count: 8,
    created_by_action: 'import',
  },
]

export const mockSettings: UserSettings = {
  personal_categories: [
    'Groceries', 'Dining', 'Transportation', 'Home', 'Health',
    'Subscriptions', 'Shopping', 'Travel', 'Entertainment',
    'Personal Care', 'Gifts', 'Other', 'Transfer', 'Income', 'Reimbursement',
  ],
  hidden_pages: [],
}

export const handlers = [
  http.get('/api/v1/auth/me', () => HttpResponse.json(mockUser)),
  http.get('/api/v1/settings', () => HttpResponse.json(mockSettings)),
  http.put('/api/v1/settings', () => HttpResponse.json(mockSettings)),
  http.get('/api/v1/settings/category-usage', () => HttpResponse.json({})),
  http.post('/api/v1/auth/login', () => HttpResponse.json({ message: 'Logged in', user: mockUser })),
  http.post('/api/v1/auth/logout', () => HttpResponse.json({ message: 'Logged out' })),

  http.get('/api/v1/transactions', ({ request }) => {
    const url = new URL(request.url)
    const classification = url.searchParams.get('classification')
    if (classification === 'unsorted') return HttpResponse.json(mockTransactions)
    return HttpResponse.json([])
  }),

  http.get('/api/v1/transactions/dashboard', () => HttpResponse.json(mockDashboard)),
  http.get('/api/v1/transactions/spending/personal', () => HttpResponse.json(mockSpending)),
  http.get('/api/v1/transactions/income/personal', () => HttpResponse.json({ ...mockSpending, total_cents: 0, points: [], by_category: [] })),

  http.post('/api/v1/transactions/bulk-classify', () => HttpResponse.json({ updated: 2 })),
  http.post('/api/v1/transactions/bulk-categorize-personal', () => HttpResponse.json({ updated: 1 })),
  http.post('/api/v1/transactions/manual', () => HttpResponse.json(mockManualTransaction, { status: 201 })),
  http.put('/api/v1/transactions/:id', () => HttpResponse.json(mockTransactions[0])),
  http.delete('/api/v1/transactions/:id', ({ params }) => {
    const id = Number(params.id)
    const tx = [...mockTransactions, mockManualTransaction].find((t) => t.id === id)
    if (!tx) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    return HttpResponse.json(tx)
  }),

  http.get('/api/v1/imports', () => HttpResponse.json(mockImportBatches)),
  http.delete('/api/v1/imports/:id', ({ params }) => {
    const id = String(params.id)
    const batch = mockImportBatches.find((b) => b.id === id)
    if (!batch) return HttpResponse.json({ detail: 'Not found' }, { status: 404 })
    return HttpResponse.json({
      removed_rows: batch.row_count,
      classified_rows: 0,
      categorized_rows: 0,
    })
  }),
]
