import { describe, expect, it } from 'vitest'
import { generateStatementCycles } from './statementCycles'

describe('generateStatementCycles', () => {
  it('returns empty for invalid statement days', () => {
    expect(generateStatementCycles(0)).toEqual([])
    expect(generateStatementCycles(32)).toEqual([])
  })

  it('builds cycles ending on the closing day, starting the day after the previous close', () => {
    // Mid-cycle: today is 5 May, closing day 21 -> current cycle is 22 Apr–21 May.
    const cycles = generateStatementCycles(21, 3, new Date(2026, 4, 5))
    expect(cycles[0]).toMatchObject({ start: '2026-04-22', end: '2026-05-21' })
    expect(cycles[1]).toMatchObject({ start: '2026-03-22', end: '2026-04-21' })
    expect(cycles[2]).toMatchObject({ start: '2026-02-22', end: '2026-03-21' })
    expect(cycles[0].label).toBe('22 Apr – 21 May')
  })

  it('rolls to next month when this month already closed', () => {
    // Today 25 May, closed on 21 May -> current cycle is 22 May–21 Jun.
    const cycles = generateStatementCycles(21, 1, new Date(2026, 4, 25))
    expect(cycles[0]).toMatchObject({ start: '2026-05-22', end: '2026-06-21' })
  })

  it('clamps closing day to short months', () => {
    // Closing day 31; February cycle should end on 28 (2026 is not a leap year).
    const cycles = generateStatementCycles(31, 2, new Date(2026, 2, 15))
    // Current cycle ends 31 Mar, starting day after Feb close (28 Feb) -> 1 Mar.
    expect(cycles[0]).toMatchObject({ start: '2026-03-01', end: '2026-03-31' })
    expect(cycles[1].end).toBe('2026-02-28')
  })

  it('generates the requested count', () => {
    expect(generateStatementCycles(15, 12)).toHaveLength(12)
  })
})
