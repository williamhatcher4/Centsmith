import { http, HttpResponse } from 'msw'
import type { DashboardSummary, SpendingSummary, Transaction, User } from '../types'

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
    statement_format: 'test',
    imported_at: '2026-05-02T12:00:00Z',
  },
]

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

export const handlers = [
  http.get('/api/v1/auth/me', () => HttpResponse.json(mockUser)),
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
  http.put('/api/v1/transactions/:id', () => HttpResponse.json(mockTransactions[0])),
]
