import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

interface Props {
  title: ReactNode
  subtitle?: ReactNode
  eyebrow?: ReactNode
  actions?: ReactNode
  className?: string
}

export function PageHeader({ title, subtitle, eyebrow, actions, className }: Props) {
  return (
    <div
      className={cn(
        'mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-6',
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-[var(--accent)]">
            {eyebrow}
          </p>
        )}
        <h1 className="font-display text-[26px] font-bold leading-[1.05] tracking-[-0.02em] text-[var(--text)] sm:text-[32px]">
          {title}
        </h1>
        {subtitle && <p className="mt-1.5 text-sm text-[var(--text-subtle)]">{subtitle}</p>}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">{actions}</div>
      )}
    </div>
  )
}
