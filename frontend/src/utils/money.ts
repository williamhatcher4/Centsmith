const CURRENCY_SYMBOL = (import.meta.env.VITE_CURRENCY_SYMBOL as string | undefined) ?? '$'
const LOCALE = (import.meta.env.VITE_LOCALE as string | undefined) ?? 'en-US'

interface FormatOptions {
  withSign?: boolean
  decimals?: 0 | 2
}

export function formatMoney(cents: number, options: FormatOptions = {}): string {
  const { withSign = false, decimals = 2 } = options
  const negative = cents < 0
  const abs = Math.abs(cents) / 100
  const body = abs.toLocaleString(LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
  if (negative) return `-${CURRENCY_SYMBOL}${body}`
  if (withSign) return `+${CURRENCY_SYMBOL}${body}`
  return `${CURRENCY_SYMBOL}${body}`
}

export function parseMoneyToCents(input: string): number {
  let cleaned = input.replace(new RegExp(`[${CURRENCY_SYMBOL}, ]`, 'g'), '').trim()
  if (!cleaned) return 0
  const isParenthesized = cleaned.startsWith('(') && cleaned.endsWith(')')
  if (isParenthesized) cleaned = cleaned.slice(1, -1)
  const negative = cleaned.startsWith('-') || isParenthesized
  cleaned = cleaned.replace(/^[+-]/, '')
  if (!/^\d*(\.\d*)?$/.test(cleaned)) return 0

  const [dollarsRaw = '0', centsRaw = ''] = cleaned.split('.')
  const dollars = Number(dollarsRaw || '0')
  if (!Number.isSafeInteger(dollars)) return 0

  const centsPadded = (centsRaw + '000').slice(0, 3)
  const cents = Number(centsPadded.slice(0, 2))
  const roundUp = Number(centsPadded[2]) >= 5 ? 1 : 0
  const total = dollars * 100 + cents + roundUp
  return negative ? -total : total
}

export const currencySymbol = CURRENCY_SYMBOL
