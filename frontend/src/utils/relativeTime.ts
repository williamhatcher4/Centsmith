/**
 * Compact relative timestamp ("just now", "5 minutes ago", "2 days ago").
 * Falls back to the locale date past a week, and to "at an unknown time" for
 * unparseable input, so callers can always interpolate the result into a
 * sentence.
 */
export function relativeTimeFrom(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return 'at an unknown time'
  const seconds = Math.max(0, Math.round((now - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return hours === 1 ? '1 hour ago' : `${hours} hours ago`
  const days = Math.round(hours / 24)
  if (days < 7) return days === 1 ? '1 day ago' : `${days} days ago`
  return `on ${new Date(then).toLocaleDateString()}`
}
