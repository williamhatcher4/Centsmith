import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../utils/cn'

type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'warning' | 'muted'

interface Props extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  size?: 'sm' | 'md'
  dot?: boolean
  customColor?: string
  children: ReactNode
}

const tones: Record<Tone, string> = {
  neutral: 'bg-[var(--surface-muted)] text-[var(--text-muted)]',
  accent: 'bg-[var(--accent-soft)] text-[var(--accent)]',
  success: 'bg-[var(--success-soft)] text-[var(--success)]',
  danger: 'bg-[var(--danger-soft)] text-[var(--danger)]',
  warning: 'bg-[var(--warning-soft)] text-[var(--warning)]',
  muted: 'bg-[var(--surface-muted)] text-[var(--text-faint)]',
}

export function Badge({
  tone = 'neutral',
  size = 'sm',
  dot,
  customColor,
  className,
  children,
  style,
  ...rest
}: Props) {
  const customStyle = customColor
    ? { backgroundColor: customColor + '1f', color: customColor, ...style }
    : style

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-semibold whitespace-nowrap',
        size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs',
        !customColor && tones[tone],
        className,
      )}
      style={customStyle}
      {...rest}
    >
      {dot && (
        <span
          aria-hidden="true"
          className="size-1.5 rounded-full bg-current"
        />
      )}
      {children}
    </span>
  )
}
