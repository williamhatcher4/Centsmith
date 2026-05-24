import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'

type CardVariant = 'glass' | 'solid' | 'muted'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const variants: Record<CardVariant, string> = {
  glass:
    'bg-[var(--surface)] backdrop-blur-xl backdrop-saturate-150 border border-[var(--border)] shadow-[var(--shadow-md)]',
  solid:
    'bg-[var(--surface-solid)] border border-[var(--border)] shadow-[var(--shadow-sm)]',
  muted:
    'bg-[var(--surface-muted)] border border-[var(--border)]',
}

const padMap = {
  none: '',
  sm: 'p-4',
  md: 'p-5 sm:p-6',
  lg: 'p-6 sm:p-8',
}

export function Card({
  variant = 'glass',
  padding = 'md',
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={cn('rounded-[var(--radius-lg)]', variants[variant], padMap[padding], className)}
      {...rest}
    >
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('mb-4 flex items-start justify-between gap-3', className)}>
      <div className="min-w-0">
        <h2 className="text-base font-semibold text-[var(--text)] leading-tight">{title}</h2>
        {subtitle && (
          <p className="mt-0.5 text-xs text-[var(--text-subtle)]">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
