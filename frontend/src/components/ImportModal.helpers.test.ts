import { describe, expect, it } from 'vitest'
import type { ImportPreview, ImportPreviewRow } from '../types'
import { defaultMappingDraft, draftToMapping, repeatGroupInfo, signedMoney } from './ImportModal.helpers'

function previewWith(detected: Record<string, number | null>, columns = 3): ImportPreview {
  return {
    rows: [], total: 0, duplicates: 0, ignored_credits: 0, to_import: 0,
    statement_format: 'Generic CSV', skipped_errors: 0, amount_sign_adjustable: false,
    charges_positive: false, skipped_rows: [], mapping_required: true,
    available_columns: Array.from({ length: columns }, (_, i) => `Col ${i}`),
    sample_rows: [], detected_columns: detected,
  }
}

function row(overrides: Partial<ImportPreviewRow> & { row_number: number }): ImportPreviewRow {
  return {
    row_number: overrides.row_number,
    date: overrides.date ?? '2026-05-01',
    description: overrides.description ?? 'Coffee',
    amount_cents: overrides.amount_cents ?? 425,
    transaction_type: overrides.transaction_type ?? 'debit',
    is_duplicate: overrides.is_duplicate ?? false,
    is_ignored_credit: overrides.is_ignored_credit ?? false,
  }
}

describe('signedMoney', () => {
  it('prefixes credits with a plus sign and debits with a minus sign', () => {
    expect(signedMoney(425, 'credit')).toBe('+$4.25')
    expect(signedMoney(425, 'debit')).toBe('-$4.25')
  })
})

describe('repeatGroupInfo', () => {
  it('ignores rows with no duplicates', () => {
    const info = repeatGroupInfo([
      row({ row_number: 1, description: 'Coffee' }),
      row({ row_number: 2, description: 'Lunch' }),
    ])
    expect(info.size).toBe(0)
  })

  it('marks every member of a duplicate group with its index and size', () => {
    const info = repeatGroupInfo([
      row({ row_number: 1, description: 'Coffee' }),
      row({ row_number: 2, description: 'Coffee' }),
      row({ row_number: 3, description: 'Coffee' }),
      row({ row_number: 4, description: 'Lunch' }),
    ])
    expect(info.get(1)).toEqual({ index: 1, size: 3 })
    expect(info.get(2)).toEqual({ index: 2, size: 3 })
    expect(info.get(3)).toEqual({ index: 3, size: 3 })
    expect(info.has(4)).toBe(false)
  })

  it('treats descriptions case-insensitively after trimming', () => {
    const info = repeatGroupInfo([
      row({ row_number: 1, description: '  Coffee  ' }),
      row({ row_number: 2, description: 'coffee' }),
    ])
    expect(info.size).toBe(2)
  })

  it('distinguishes rows that differ on date or amount or type', () => {
    const info = repeatGroupInfo([
      row({ row_number: 1, description: 'Coffee', amount_cents: 425 }),
      row({ row_number: 2, description: 'Coffee', amount_cents: 500 }),
      row({ row_number: 3, description: 'Coffee', date: '2026-05-02' }),
      row({ row_number: 4, description: 'Coffee', transaction_type: 'credit' }),
    ])
    expect(info.size).toBe(0)
  })
})

describe('defaultMappingDraft', () => {
  it('uses detected indices and single-amount mode when no debit/credit found', () => {
    const draft = defaultMappingDraft(previewWith({ date: 0, description: 1, amount: 2, debit: null, credit: null }))
    expect(draft).toMatchObject({ date_column: 0, description_column: 1, amount_mode: 'single', amount_column: 2 })
  })

  it('chooses split mode when a debit or credit column is detected', () => {
    const draft = defaultMappingDraft(previewWith({ date: 0, description: 1, amount: null, debit: 2, credit: 3 }, 4))
    expect(draft.amount_mode).toBe('split')
    expect(draft).toMatchObject({ debit_column: 2, credit_column: 3 })
  })

  it('falls back to distinct free columns when nothing is detected', () => {
    const draft = defaultMappingDraft(previewWith({ date: null, description: null, amount: null, debit: null, credit: null }))
    expect(draft.date_column).not.toBe(draft.description_column)
  })
})

describe('draftToMapping', () => {
  it('emits an amount column + convention in single mode', () => {
    const mapping = draftToMapping({ date_column: 0, description_column: 1, amount_mode: 'single', amount_column: 2, debit_column: 3, credit_column: 4, amount_convention: 'charges_positive' })
    expect(mapping).toEqual({ date_column: 0, description_column: 1, amount_column: 2, amount_convention: 'charges_positive' })
  })

  it('emits debit/credit columns in split mode and drops the amount column', () => {
    const mapping = draftToMapping({ date_column: 0, description_column: 1, amount_mode: 'split', amount_column: 2, debit_column: 3, credit_column: 4, amount_convention: 'signed' })
    expect(mapping).toEqual({ date_column: 0, description_column: 1, debit_column: 3, credit_column: 4, amount_convention: 'signed' })
  })
})
