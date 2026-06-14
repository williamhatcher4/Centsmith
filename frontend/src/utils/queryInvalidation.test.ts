import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import {
  ANALYTICS_QUERY_KEYS,
  LEDGER_QUERY_KEYS,
  invalidateAnalytics,
  invalidateLedger,
} from './queryInvalidation'

// Query-key roots that do not hold transaction rows or transaction-derived
// aggregates, so transaction mutations never need to invalidate them.
// ('settings' moved to LEDGER_QUERY_KEYS: categorizing a transaction can
// auto-register a new personal category in UserSettings.)
const NON_TRANSACTION_KEYS = ['auth', 'cards', 'import-profiles', 'maintenance']

// Raw source of every non-test module under src/, so the guard sees new query
// keys the moment they are added anywhere in the app.
const sourceFiles = import.meta.glob('../**/*.{ts,tsx}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function collectQueryKeyRoots(): Set<string> {
  const roots = new Set<string>()
  const pattern = /queryKey:\s*\[\s*'([^']+)'/g
  for (const [file, text] of Object.entries(sourceFiles)) {
    if (/\.test\./.test(file)) continue
    for (const match of text.matchAll(pattern)) roots.add(match[1])
  }
  return roots
}

describe('invalidateLedger', () => {
  it('invalidates the transaction list, import history, and settings (auto-added categories)', () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    invalidateLedger(qc)
    expect(spy.mock.calls.map((call) => call[0]?.queryKey)).toEqual([['transactions'], ['imports'], ['settings']])
  })

  it('refreshes the settings cache so a category auto-added by categorize appears in dropdowns', () => {
    // P3.3: PUT/bulk-categorize can append an unknown category to
    // UserSettings.personal_categories server-side; every categorize mutation
    // site calls invalidateLedger, so ['settings'] must be in its key set.
    expect(LEDGER_QUERY_KEYS.map((k) => k[0])).toContain('settings')
  })
})

describe('invalidateAnalytics', () => {
  it('invalidates every transaction-derived aggregate', () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, 'invalidateQueries')
    invalidateAnalytics(qc)
    expect(spy.mock.calls.map((call) => call[0]?.queryKey)).toEqual([
      ['spending'], ['income'], ['dashboard'], ['statement'],
    ])
  })
})

describe('query-key drift guard', () => {
  it('every query key used in the app is either covered by a helper or known non-transaction data', () => {
    const covered = new Set<string>([
      ...LEDGER_QUERY_KEYS.map((k) => k[0]),
      ...ANALYTICS_QUERY_KEYS.map((k) => k[0]),
      ...NON_TRANSACTION_KEYS,
    ])
    const roots = collectQueryKeyRoots()
    expect(roots.size).toBeGreaterThan(0)
    for (const root of roots) {
      expect(
        covered.has(root),
        `query key root '${root}' is not covered by invalidateLedger/invalidateAnalytics — ` +
          'add it to the right helper in utils/queryInvalidation.ts (or to NON_TRANSACTION_KEYS here if it never holds transaction-derived data)',
      ).toBe(true)
    }
  })
})
