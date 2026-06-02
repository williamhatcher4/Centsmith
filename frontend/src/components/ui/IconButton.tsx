import { type ButtonHTMLAttributes, type ReactNode, type Ref } from 'react'
import { cn } from '../../utils/cn'

type Variant = 'ghost' | 'subtle' | 'danger'
type Size = 'sm' | 'md'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  icon: ReactNode
  'aria-label': string
  ref?: Ref<HTMLButtonElement>
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

export function IconButton({
  variant = 'ghost',
  size = 'md',
  icon,
  className,
  type = 'button',
  ref,
  ...rest
}: Props) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex items-center justify-center rounded-[var(--radius-sm)]',
        'transition-[transform,background-color,color] duration-150 ease-[var(--ease-out)]',
        'cursor-pointer disabled:opacity-50 disabled:active:scale-100 active:scale-[0.92]',
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {icon}
    </button>
  )
}
