import { createContext, use } from 'react'

export type Theme = 'light' | 'dark'

export type Accent = 'indigo' | 'violet' | 'cyan' | 'emerald' | 'rose' | 'amber'

export interface AccentDef {
  id: Accent
  label: string
  /** Swatch color shown in the picker (matches the light-mode base hue). */
  swatch: string
}

export const ACCENTS: AccentDef[] = [
  { id: 'indigo', label: 'Indigo', swatch: '#6366F1' },
  { id: 'violet', label: 'Violet', swatch: '#8B5CF6' },
  { id: 'cyan', label: 'Cyan', swatch: '#06B6D4' },
  { id: 'emerald', label: 'Emerald', swatch: '#10B981' },
  { id: 'rose', label: 'Rose', swatch: '#F43F5E' },
  { id: 'amber', label: 'Amber', swatch: '#F59E0B' },
]

export const ACCENT_IDS = ACCENTS.map((a) => a.id)

export interface ThemeContextValue {
  theme: Theme
  toggle: () => void
  setTheme: (t: Theme) => void
  accent: Accent
  setAccent: (a: Accent) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme() {
  const ctx = use(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}
