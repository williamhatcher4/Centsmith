import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../utils/cn'

type Variant = 'ghost' | 'subtle' | 'danger'
type Size = 'sm' | 'md'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon: ReactNode
  'aria-label': string
}

const variants: Record<Variant, string> = {
  ghost:
    'bg-transparent text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)]',
  subtle:
    'bg-[var(--surface-muted)] text-[var(--text-muted)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]',
  danger:
    'bg-transparent text-[var(--text-faint)] hover:bg-[var(--danger-soft)] hover:text-[var(--danger)]',
}

const sizes: Record<Size, string> = {
  sm: 'size-8',
  md: 'size-10',
}

export const IconButton = forwardRef<HTMLButtonElement, Props>(function IconButton(
  { variant = 'ghost', size = 'md', icon, className, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex items-center justify-center rounded-[var(--radius-sm)]',
        'transition-colors duration-150 cursor-pointer disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {icon}
    </button>
  )
})
