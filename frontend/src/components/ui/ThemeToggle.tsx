import { Sun, Moon } from 'lucide-react'
import { useTheme } from './theme'
import { IconButton } from './IconButton'

export function ThemeToggle({ size = 'md' }: { size?: 'sm' | 'md' }) {
  const { theme, toggle } = useTheme()
  const isDark = theme === 'dark'
  return (
    <IconButton
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      onClick={toggle}
      size={size}
      icon={isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
    />
  )
}
