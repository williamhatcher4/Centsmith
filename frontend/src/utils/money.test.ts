import { describe, expect, it } from 'vitest'
import { formatMoney, parseMoneyToCents } from './money'

describe('formatMoney', () => {
  it('formats positive amounts with two decimals and commas', () => {
    expect(formatMoney(123456)).toBe('$1,234.56')
    expect(formatMoney(0)).toBe('$0.00')
    expect(formatMoney(99)).toBe('$0.99')
  })

  it('prefixes negative amounts with a minus sign', () => {
    expect(formatMoney(-425)).toBe('-$4.25')
    expect(formatMoney(-100000000)).toBe('-$1,000,000.00')
  })

  it('adds a plus prefix when withSign is true and value is positive', () => {
    expect(formatMoney(425, { withSign: true })).toBe('+$4.25')
  })

  it('uses the minus prefix even when withSign is requested for negatives', () => {
    expect(formatMoney(-425, { withSign: true })).toBe('-$4.25')
  })

  it('supports zero-decimal formatting for stat cards', () => {
    expect(formatMoney(123456, { decimals: 0 })).toBe('$1,235')
    expect(formatMoney(-425, { decimals: 0 })).toBe('-$4')
  })
})

describe('parseMoneyToCents', () => {
  it('parses plain dollar amounts', () => {
    expect(parseMoneyToCents('1234.56')).toBe(123456)
    expect(parseMoneyToCents('0')).toBe(0)
  })

  it('strips currency symbols and commas', () => {
    expect(parseMoneyToCents('$1,234.56')).toBe(123456)
    expect(parseMoneyToCents(' $1,234.56 ')).toBe(123456)
  })

  it('handles minus-sign and parenthesis negatives', () => {
    expect(parseMoneyToCents('-4.25')).toBe(-425)
    expect(parseMoneyToCents('-$4.25')).toBe(-425)
    expect(parseMoneyToCents('(4.25)')).toBe(-425)
  })

  it('returns zero for empty or garbage input', () => {
    expect(parseMoneyToCents('')).toBe(0)
    expect(parseMoneyToCents('not-a-number')).toBe(0)
    expect(parseMoneyToCents('1.2.3')).toBe(0)
  })

  it('rounds the third decimal half up', () => {
    expect(parseMoneyToCents('0.005')).toBe(1)
    expect(parseMoneyToCents('0.004')).toBe(0)
  })

  it('round-trips with formatMoney for representative amounts', () => {
    for (const cents of [0, 1, 99, 100, 123456, -425, -100000000]) {
      expect(parseMoneyToCents(formatMoney(cents))).toBe(cents)
    }
  })
})
