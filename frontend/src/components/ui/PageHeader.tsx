import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

interface Props {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, actions, className }: Props) {
  return (
    <div
      className={cn(
        'mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 sm:gap-6',
        className,
      )}
    >
      <div className="min-w-0">
        <h1 className="text-2xl sm:text-[28px] font-bold tracking-tight text-[var(--text)] leading-tight">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 text-sm text-[var(--text-subtle)]">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">{actions}</div>
      )}
    </div>
  )
}
