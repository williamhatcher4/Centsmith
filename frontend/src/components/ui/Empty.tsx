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
        'relative flex flex-col items-center justify-center overflow-hidden text-center',
        'rounded-[var(--radius-lg)] bg-[var(--surface)] backdrop-blur-xl',
        'border border-dashed border-[var(--border-strong)]',
        'px-6 py-12 sm:px-10 sm:py-14',
        className,
      )}
    >
      {/* soft ambient glow behind the icon */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-1/2 top-6 size-32 -translate-x-1/2 rounded-full opacity-50 blur-3xl"
        style={{ background: 'radial-gradient(circle at center, var(--glow-1), transparent 70%)' }}
      />
      {icon && (
        <div className="relative mb-3 flex size-12 items-center justify-center rounded-2xl bg-[image:var(--grad-brand-soft)] text-[var(--accent)] ring-1 ring-inset ring-[var(--border)]">
          {icon}
        </div>
      )}
      <p className="relative font-display text-lg font-semibold text-[var(--text)]">{title}</p>
      {description && (
        <p className="relative mt-1 max-w-md text-sm text-[var(--text-subtle)]">{description}</p>
      )}
      {action && <div className="relative mt-5">{action}</div>}
    </div>
  )
}
