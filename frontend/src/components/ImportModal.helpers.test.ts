import { describe, expect, it } from 'vitest'
import type { ImportPreviewRow } from '../types'
import { repeatGroupInfo, signedMoney } from './ImportModal.helpers'

function row(overrides: Partial<ImportPreviewRow> & { row_number: number }): ImportPreviewRow {
  return {
    row_number: overrides.row_number,
    date: overrides.date ?? '2026-05-01',
    description: overrides.description ?? 'Coffee',
    amount_cents: overrides.amount_cents ?? 425,
    transaction_type: overrides.transaction_type ?? 'debit',
    is_duplicate: overrides.is_duplicate ?? false,
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
