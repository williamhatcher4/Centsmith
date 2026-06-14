import type { InfiniteData } from '@tanstack/react-query'
import type { Transaction, TransactionPage } from '../types'

// The transaction caches hold either a single TransactionPage (inbox queries) or
// an InfiniteData<TransactionPage> (the Transactions page's paginated list). Apply
// an update/remove to a row across whichever shape a cache entry holds; returning
// null from `fn` drops the row.
export type TxCache = TransactionPage | InfiniteData<TransactionPage>

export function patchPage(page: TransactionPage, fn: (tx: Transaction) => Transaction | null): TransactionPage {
  const items: Transaction[] = []
  for (const tx of page.items) {
    const next = fn(tx)
    if (next) items.push(next)
  }
  return { ...page, items }
}

export function patchTxCache(current: TxCache | undefined, fn: (tx: Transaction) => Transaction | null): TxCache | undefined {
  if (!current) return current
  if ('pages' in current) {
    return { ...current, pages: current.pages.map((p) => patchPage(p, fn)) }
  }
  return patchPage(current, fn)
}
