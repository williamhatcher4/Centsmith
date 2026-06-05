export interface StatementCycle {
  start: string // yyyy-mm-dd (inclusive)
  end: string // yyyy-mm-dd (inclusive, the statement closing day)
  label: string
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function daysInMonth(year: number, monthIndex: number): number {
  return new Date(year, monthIndex + 1, 0).getDate()
}

/** Date the statement closes for a given month, clamped to the month's length. */
function closingDate(year: number, monthIndex: number, statementDay: number): Date {
  const day = Math.min(statementDay, daysInMonth(year, monthIndex))
  return new Date(year, monthIndex, day)
}

function shiftMonth(year: number, monthIndex: number, delta: number): [number, number] {
  const total = year * 12 + monthIndex + delta
  return [Math.floor(total / 12), ((total % 12) + 12) % 12]
}

function toISO(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function readable(date: Date): string {
  return `${date.getDate()} ${MONTHS[date.getMonth()]}`
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

/**
 * Generate the most recent `count` statement cycles for a card that closes on
 * `statementDay` each month. Cycle 0 (newest) is the one currently in progress
 * or just closed; each cycle runs from the day after the previous close through
 * the close date (both inclusive). Closing days are clamped to short months
 * (e.g. day 31 → 28/29/30).
 */
export function generateStatementCycles(
  statementDay: number,
  count = 12,
  today: Date = new Date(),
): StatementCycle[] {
  if (!statementDay || statementDay < 1 || statementDay > 31) return []

  // Anchor the newest cycle on the first closing date that is on/after today,
  // so a mid-cycle period shows the in-progress statement as the newest entry.
  let [baseYear, baseMonth] = [today.getFullYear(), today.getMonth()]
  const thisClose = closingDate(baseYear, baseMonth, statementDay)
  const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  if (thisClose < todayMidnight) {
    ;[baseYear, baseMonth] = shiftMonth(baseYear, baseMonth, 1)
  }

  const cycles: StatementCycle[] = []
  for (let i = 0; i < count; i++) {
    const [ey, em] = shiftMonth(baseYear, baseMonth, -i)
    const endDate = closingDate(ey, em, statementDay)
    const [py, pm] = shiftMonth(ey, em, -1)
    const startDate = addDays(closingDate(py, pm, statementDay), 1)
    cycles.push({
      start: toISO(startDate),
      end: toISO(endDate),
      label: `${readable(startDate)} – ${readable(endDate)}`,
    })
  }
  return cycles
}
