import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { cn } from '../../utils/cn'
import { useReducedMotion } from '../../hooks/useReducedMotion'

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

interface ThumbRect {
  left: number
  top: number
  width: number
  height: number
}

export function SegmentedControl<T extends string | number>({
  value,
  onChange,
  options,
  size = 'md',
  className,
  ...rest
}: Props<T>) {
  const reduced = useReducedMotion()
  const btnRefs = useRef<(HTMLButtonElement | null)[]>([])
  const [thumb, setThumb] = useState<ThumbRect | null>(null)
  const activeIndex = options.findIndex((o) => o.value === value)

  useLayoutEffect(() => {
    const el = btnRefs.current[activeIndex]
    if (!el) return
    setThumb({ left: el.offsetLeft, top: el.offsetTop, width: el.offsetWidth, height: el.offsetHeight })
  }, [activeIndex, options.length, size])

  return (
    <div
      role="tablist"
      aria-label={rest['aria-label']}
      className={cn(
        'relative inline-flex items-center rounded-[var(--radius-sm)] border border-[var(--border)] bg-[var(--surface-muted)] p-1',
        className,
      )}
    >
      {thumb && thumb.width > 0 && (
        <span
          aria-hidden="true"
          className="absolute rounded-[6px] bg-[var(--surface-solid)] shadow-[var(--shadow-sm)]"
          style={{
            left: thumb.left,
            top: thumb.top,
            width: thumb.width,
            height: thumb.height,
            transition: reduced
              ? undefined
              : 'left 220ms var(--ease-out), width 220ms var(--ease-out)',
          }}
        />
      )}
      {options.map((opt, i) => {
        const active = opt.value === value
        return (
          <button
            key={String(opt.value)}
            ref={(el) => {
              btnRefs.current[i] = el
            }}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(opt.value)}
            className={cn(
              'relative z-10 inline-flex items-center justify-center rounded-[6px] font-semibold transition-colors duration-150 ease-[var(--ease-out)] cursor-pointer',
              size === 'sm' ? 'h-7 px-3 text-xs' : 'h-8 px-4 text-xs',
              active ? 'text-[var(--accent)]' : 'text-[var(--text-subtle)] hover:text-[var(--text)]',
            )}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
