import { describe, expect, it } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { useCategories } from './useCategories'

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } } })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

describe('useCategories', () => {
  it('returns spending without Income/Reimbursement', async () => {
    const { result } = renderHook(() => useCategories(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.spending.length).toBeGreaterThan(0))
    expect(result.current.spending).not.toContain('Income')
    expect(result.current.spending).not.toContain('Reimbursement')
    expect(result.current.spending).toContain('Groceries')
    expect(result.current.spending).toContain('Transfer')
  })

  it('returns credit list with Income/Reimbursement first', async () => {
    const { result } = renderHook(() => useCategories(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.credit.length).toBeGreaterThan(0))
    expect(result.current.credit.slice(0, 2)).toEqual(['Income', 'Reimbursement'])
  })

  it('flags system categories', async () => {
    const { result } = renderHook(() => useCategories(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.all.length).toBeGreaterThan(0))
    expect(result.current.isSystem('Income')).toBe(true)
    expect(result.current.isSystem('Transfer')).toBe(true)
    expect(result.current.isSystem('Groceries')).toBe(false)
  })

  it('reflects user-added categories', async () => {
    server.use(
      http.get('/api/v1/settings', () =>
        HttpResponse.json({
          personal_categories: ['Coffee', 'Tea', 'Income', 'Reimbursement', 'Transfer'],
          hidden_pages: [],
        }),
      ),
    )
    const { result } = renderHook(() => useCategories(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.all).toContain('Coffee'))
    expect(result.current.spending).toContain('Coffee')
    expect(result.current.spending).toContain('Tea')
    expect(result.current.spending).not.toContain('Income')
  })

  it('categoriesFor returns credit list for credit transactions', async () => {
    const { result } = renderHook(() => useCategories(), { wrapper: wrap() })
    await waitFor(() => expect(result.current.all.length).toBeGreaterThan(0))
    const credit = result.current.categoriesFor({ transaction_type: 'credit' })
    const debit = result.current.categoriesFor({ transaction_type: 'debit' })
    expect(credit).toContain('Income')
    expect(debit).not.toContain('Income')
  })
})
