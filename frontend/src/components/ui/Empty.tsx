import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

interface Props {
  icon?: ReactNode
  title: ReactNode
  description?: ReactNode
  action?: ReactNode
  className?: string
}

export function Empty({ icon, title, description, action, className }: Props) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        'rounded-[var(--radius-lg)] bg-[var(--surface)] backdrop-blur-xl',
        'border border-dashed border-[var(--border-strong)]',
        'px-6 py-12 sm:px-10 sm:py-14',
        className,
      )}
    >
      {icon && (
        <div className="mb-3 flex size-12 items-center justify-center rounded-full bg-[var(--accent-soft)] text-[var(--accent)]">
          {icon}
        </div>
      )}
      <p className="text-base font-semibold text-[var(--text)]">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-[var(--text-subtle)]">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}
