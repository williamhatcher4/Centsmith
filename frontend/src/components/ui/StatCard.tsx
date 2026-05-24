import type { ReactNode } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { cn } from '../../utils/cn'

type Tone = 'neutral' | 'positive' | 'negative' | 'accent'

interface Props {
  label: ReactNode
  value: ReactNode
  tone?: Tone
  icon?: ReactNode
  trend?: { direction: 'up' | 'down' | 'flat'; label: string }
  hint?: ReactNode
  className?: string
}

const toneMap: Record<Tone, string> = {
  neutral: 'text-[var(--text)]',
  positive: 'text-[var(--success)]',
  negative: 'text-[var(--danger)]',
  accent: 'text-[var(--accent)]',
}

const iconBgMap: Record<Tone, string> = {
  neutral: 'bg-[var(--surface-muted)] text-[var(--text-muted)]',
  positive: 'bg-[var(--success-soft)] text-[var(--success)]',
  negative: 'bg-[var(--danger-soft)] text-[var(--danger)]',
  accent: 'bg-[var(--accent-soft)] text-[var(--accent)]',
}

export function StatCard({ label, value, tone = 'neutral', icon, trend, hint, className }: Props) {
  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-[var(--radius-lg)]',
        'bg-[var(--surface)] backdrop-blur-xl backdrop-saturate-150',
        'border border-[var(--border)] shadow-[var(--shadow-sm)]',
        'px-5 py-4 sm:px-6 sm:py-5',
        'transition-shadow duration-200 hover:shadow-[var(--shadow-md)]',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-subtle)]">{label}</div>
        {icon && (
          <div className={cn('flex size-9 items-center justify-center rounded-full', iconBgMap[tone])}>
            {icon}
          </div>
        )}
      </div>
      <div
        className={cn(
          'mt-2 text-2xl sm:text-3xl font-bold tabular-nums leading-tight tracking-tight',
          toneMap[tone],
        )}
      >
        {value}
      </div>
      {(trend || hint) && (
        <div className="mt-2 flex items-center gap-2 text-xs text-[var(--text-subtle)]">
          {trend && (
            <span
              className={cn(
                'inline-flex items-center gap-1 font-semibold',
                trend.direction === 'up' && 'text-[var(--success)]',
                trend.direction === 'down' && 'text-[var(--danger)]',
                trend.direction === 'flat' && 'text-[var(--text-subtle)]',
              )}
            >
              {trend.direction === 'up' && <TrendingUp className="size-3.5" />}
              {trend.direction === 'down' && <TrendingDown className="size-3.5" />}
              {trend.label}
            </span>
          )}
          {hint && <span>{hint}</span>}
        </div>
      )}
    </div>
  )
}
