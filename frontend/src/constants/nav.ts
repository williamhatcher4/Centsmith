import { BarChart3, CreditCard, Download, Inbox, ReceiptText, Settings as SettingsIcon, Tags, TrendingDown } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavLinkDef {
  to: string
  label: string
  icon: LucideIcon
  hideable: boolean
}

export const NAV_LINKS: NavLinkDef[] = [
  { to: '/', label: 'Dashboard', icon: BarChart3, hideable: true },
  { to: '/inbox', label: 'Inbox', icon: Inbox, hideable: true },
  { to: '/personal-inbox', label: 'Personal Inbox', icon: Tags, hideable: true },
  { to: '/transactions', label: 'Transactions', icon: ReceiptText, hideable: true },
  { to: '/spending', label: 'Spending', icon: TrendingDown, hideable: true },
  { to: '/exports', label: 'Exports', icon: Download, hideable: true },
  { to: '/statements', label: 'Statements', icon: CreditCard, hideable: true },
  { to: '/settings', label: 'Settings', icon: SettingsIcon, hideable: false },
]

export const HIDEABLE_NAV_LINKS = NAV_LINKS.filter((l) => l.hideable)

export function visibleLinks(hiddenPages: readonly string[]): NavLinkDef[] {
  const hidden = new Set(hiddenPages)
  return NAV_LINKS.filter((l) => !l.hideable || !hidden.has(l.to))
}
