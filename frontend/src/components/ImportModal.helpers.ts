import type { ImportPreviewRow } from '../types'
import { formatMoney } from '../utils/money'

export function signedMoney(cents: number, type: 'credit' | 'debit') {
  return `${type === 'credit' ? '+' : '-'}${formatMoney(cents)}`
}

export function repeatGroupInfo(rows: ImportPreviewRow[]): Map<number, { index: number; size: number }> {
  const groups = new Map<string, number[]>()
  for (const row of rows) {
    const key = `${row.date}|${row.description.trim().toLowerCase()}|${row.amount_cents}|${row.transaction_type}`
    const bucket = groups.get(key) ?? []
    bucket.push(row.row_number)
    groups.set(key, bucket)
  }
  const result = new Map<number, { index: number; size: number }>()
  for (const bucket of groups.values()) {
    if (bucket.length < 2) continue
    bucket.forEach((rowNumber, idx) => {
      result.set(rowNumber, { index: idx + 1, size: bucket.length })
    })
  }
  return result
}
