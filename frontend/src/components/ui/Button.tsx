import { type ButtonHTMLAttributes, type ReactNode, type Ref } from 'react'
import { cn } from '../../utils/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle'
type Size = 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  leftIcon?: ReactNode
  rightIcon?: ReactNode
  loading?: boolean
  fullWidth?: boolean
  ref?: Ref<HTMLButtonElement>
}

const variants: Record<Variant, string> = {
  primary:
    'text-white bg-[image:var(--grad-brand)] shadow-[var(--shadow-sm)] hover:shadow-[var(--shadow-glow)] hover:brightness-[1.06] active:scale-[0.97]',
  secondary:
    'bg-[var(--surface-strong)] backdrop-blur-md text-[var(--text)] border border-[var(--border-strong)] hover:border-[var(--accent-ring)] hover:bg-[var(--surface-solid)] active:scale-[0.97]',
  ghost:
    'bg-transparent text-[var(--text-muted)] hover:bg-[var(--surface-muted)] hover:text-[var(--text)] active:scale-[0.97]',
  danger:
    'bg-[var(--danger-soft)] text-[var(--danger)] border border-transparent hover:bg-[var(--danger)] hover:text-white active:scale-[0.97]',
  subtle:
    'bg-[var(--accent-soft)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white active:scale-[0.97]',
}

const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-10 px-4 text-sm gap-2',
  lg: 'h-11 px-5 text-sm gap-2',
}

export function Button({
  variant = 'primary',
  size = 'md',
  leftIcon,
  rightIcon,
  loading,
  fullWidth,
  className,
  children,
  disabled,
  type = 'button',
  ref,
  ...rest
}: Props) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center rounded-[var(--radius-sm)] font-semibold',
        'transition-[transform,box-shadow,background-color,border-color,color,filter] duration-150 ease-[var(--ease-out)]',
        'disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100 cursor-pointer',
        variants[variant],
        sizes[size],
        fullWidth && 'w-full',
        className,
      )}
      {...rest}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="inline-block size-4 rounded-full border-2 border-current border-r-transparent animate-spin"
        />
      ) : (
        leftIcon
      )}
      {children}
      {!loading && rightIcon}
    </button>
  )
}
