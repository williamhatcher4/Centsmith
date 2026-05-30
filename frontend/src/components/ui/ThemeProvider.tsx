import { useEffect, useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import { ThemeContext, ACCENT_IDS, type Theme, type Accent } from './theme'

const STORAGE_KEY = 'asset-tracker:theme'
const ACCENT_KEY = 'asset-tracker:accent'

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return 'light'
}

function getInitialAccent(): Accent {
  if (typeof window === 'undefined') return 'indigo'
  const saved = localStorage.getItem(ACCENT_KEY)
  return saved && (ACCENT_IDS as string[]).includes(saved) ? (saved as Accent) : 'indigo'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme)
  const [accent, setAccentState] = useState<Accent>(getInitialAccent)

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  useEffect(() => {
    const root = document.documentElement
    // Indigo is the baseline (no attribute) so the default ships unchanged.
    if (accent === 'indigo') root.removeAttribute('data-accent')
    else root.dataset.accent = accent
    localStorage.setItem(ACCENT_KEY, accent)
  }, [accent])

  const setTheme = useCallback((t: Theme) => setThemeState(t), [])
  const toggle = useCallback(() => setThemeState((t) => (t === 'light' ? 'dark' : 'light')), [])
  const setAccent = useCallback((a: Accent) => setAccentState(a), [])

  return (
    <ThemeContext.Provider value={{ theme, toggle, setTheme, accent, setAccent }}>
      {children}
    </ThemeContext.Provider>
  )
}
