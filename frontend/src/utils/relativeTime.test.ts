import { describe, expect, it } from 'vitest'
import { relativeTimeFrom } from './relativeTime'

const NOW = Date.parse('2026-06-09T12:00:00Z')

describe('relativeTimeFrom', () => {
  it('reports very recent times as just now', () => {
    expect(relativeTimeFrom('2026-06-09T11:59:30Z', NOW)).toBe('just now')
    expect(relativeTimeFrom('2026-06-09T12:00:00Z', NOW)).toBe('just now')
  })

  it('treats slight clock skew into the future as just now', () => {
    expect(relativeTimeFrom('2026-06-09T12:00:20Z', NOW)).toBe('just now')
  })

  it('formats minutes and hours with singular forms', () => {
    expect(relativeTimeFrom('2026-06-09T11:59:00Z', NOW)).toBe('1 minute ago')
    expect(relativeTimeFrom('2026-06-09T11:35:00Z', NOW)).toBe('25 minutes ago')
    expect(relativeTimeFrom('2026-06-09T11:00:00Z', NOW)).toBe('1 hour ago')
    expect(relativeTimeFrom('2026-06-09T05:00:00Z', NOW)).toBe('7 hours ago')
  })

  it('formats recent days then falls back to a date', () => {
    expect(relativeTimeFrom('2026-06-08T12:00:00Z', NOW)).toBe('1 day ago')
    expect(relativeTimeFrom('2026-06-06T12:00:00Z', NOW)).toBe('3 days ago')
    expect(relativeTimeFrom('2026-05-01T12:00:00Z', NOW)).toMatch(/^on /)
  })

  it('handles unparseable input', () => {
    expect(relativeTimeFrom('not-a-date', NOW)).toBe('at an unknown time')
  })
})
