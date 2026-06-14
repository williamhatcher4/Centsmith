import type { QueryClient } from '@tanstack/react-query'

// Shared invalidation sets for mutations that change transaction rows. Before
// this module every mutation site hand-rolled its own list with varying
// completeness (e.g. classify forgot 'income'); add new query keys here, not
// at the call sites.

/** Row-level data: the transaction list and the import-batch history, plus
 * settings — categorizing can auto-register a new personal category there. */
export const LEDGER_QUERY_KEYS = [['transactions'], ['imports'], ['settings']] as const

/** Derived analytics: every aggregate computed from transaction rows. */
export const ANALYTICS_QUERY_KEYS = [['spending'], ['income'], ['dashboard'], ['statement']] as const

export function invalidateLedger(qc: QueryClient) {
  for (const queryKey of LEDGER_QUERY_KEYS) qc.invalidateQueries({ queryKey: [...queryKey] })
}

export function invalidateAnalytics(qc: QueryClient) {
  for (const queryKey of ANALYTICS_QUERY_KEYS) qc.invalidateQueries({ queryKey: [...queryKey] })
}
