import type { ReactNode } from 'react'
import { cn } from '../../utils/cn'

interface Option<T extends string | number> {
  value: T
  label: ReactNode
}

interface Props<T extends string | number> {
  value: T
  onChange: (v: T) => void
  options: Option<T>[]
  size?: 'sm' | 'md'
  className?: string
  'aria-label'?: string
}

export function SegmentedControl<T extends string | number>({
  value,
  onChange,
  options,
  size = 'md',
  className,
  ...rest
}: Props<T>) {
  return (
    <div
      role="tablist"
      aria-label={rest['aria-label']}
      className={cn(
        'inline-flex items-center rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface-muted)] p-1',
        className,
      )}
    >
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={String(opt.value)}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              'inline-flex items-center justify-center rounded-[6px] font-semibold transition-all duration-150 cursor-pointer',
              size === 'sm' ? 'h-7 px-3 text-xs' : 'h-8 px-4 text-xs',
              active
                ? 'bg-[var(--surface-solid)] text-[var(--accent)] shadow-[var(--shadow-sm)]'
                : 'text-[var(--text-subtle)] hover:text-[var(--text)]',
            )}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
