import type { AmountConvention, ColumnMapping, ImportPreview, ImportPreviewRow } from '../types'
import { formatMoney } from '../utils/money'

export function signedMoney(cents: number, type: 'credit' | 'debit') {
  return `${type === 'credit' ? '+' : '-'}${formatMoney(cents)}`
}

export interface MappingDraft {
  date_column: number
  description_column: number
  amount_mode: 'single' | 'split'
  amount_column: number
  debit_column: number
  credit_column: number
  amount_convention: AmountConvention
}

/** Build a sensible default mapping draft from a preview's detected columns. */
export function defaultMappingDraft(preview: ImportPreview): MappingDraft {
  const detected = preview.detected_columns ?? {}
  const count = preview.available_columns.length
  const firstFree = (...taken: number[]) => {
    for (let i = 0; i < count; i++) if (!taken.includes(i)) return i
    return 0
  }
  const date = detected.date ?? 0
  const description = detected.description ?? firstFree(date)
  const hasSplit = detected.debit != null || detected.credit != null
  const amount = detected.amount ?? firstFree(date, description)
  return {
    date_column: date,
    description_column: description,
    amount_mode: hasSplit ? 'split' : 'single',
    amount_column: amount,
    debit_column: detected.debit ?? firstFree(date, description),
    credit_column: detected.credit ?? firstFree(date, description),
    amount_convention: 'signed',
  }
}

/** Convert a draft into the wire ColumnMapping the API expects. */
export function draftToMapping(draft: MappingDraft): ColumnMapping {
  if (draft.amount_mode === 'split') {
    return {
      date_column: draft.date_column,
      description_column: draft.description_column,
      debit_column: draft.debit_column,
      credit_column: draft.credit_column,
      amount_convention: 'signed',
    }
  }
  return {
    date_column: draft.date_column,
    description_column: draft.description_column,
    amount_column: draft.amount_column,
    amount_convention: draft.amount_convention,
  }
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
