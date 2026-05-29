import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { cn } from '../../utils/cn'
import { IconButton } from './IconButton'

type Size = 'sm' | 'md' | 'lg' | 'xl'

interface Props {
  open: boolean
  onClose: () => void
  title?: ReactNode
  subtitle?: ReactNode
  size?: Size
  children: ReactNode
  footer?: ReactNode
  /** Disable outside-click and ESC dismissal (e.g., during async confirm). */
  dismissible?: boolean
  className?: string
}

const sizeMap: Record<Size, string> = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md',
  lg: 'sm:max-w-2xl',
  xl: 'sm:max-w-4xl',
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  size = 'md',
  children,
  footer,
  dismissible = true,
  className,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (dismissible && e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onClose, dismissible])

  useEffect(() => {
    if (open) dialogRef.current?.focus()
  }, [open])

  if (!open) return null

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center"
      onMouseDown={(e) => {
        if (dismissible && e.target === e.currentTarget) onClose()
      }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/45 backdrop-blur-md animate-[fadeIn_200ms_var(--ease-out)]" />

      {/* Dialog */}
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={cn(
          'relative w-full sm:w-[min(92vw,640px)] max-h-[92vh] flex flex-col',
          'bg-[var(--surface-strong)] backdrop-blur-2xl backdrop-saturate-150',
          'border border-[var(--border-strong)] shadow-[var(--shadow-lg)]',
          'ring-1 ring-inset ring-white/10',
          'rounded-t-[var(--radius-xl)] sm:rounded-[var(--radius-xl)]',
          'animate-[slideUp_280ms_var(--ease-drawer)]',
          'focus:outline-none',
          sizeMap[size],
          className,
        )}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {(title || dismissible) && (
          <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-5 sm:px-6 py-4">
            <div className="min-w-0">
              {title && <h2 className="text-lg font-semibold text-[var(--text)] leading-tight">{title}</h2>}
              {subtitle && <p className="mt-1 text-xs text-[var(--text-subtle)]">{subtitle}</p>}
            </div>
            {dismissible && (
              <IconButton
                aria-label="Close"
                onClick={onClose}
                icon={<X className="size-4" />}
                size="sm"
              />
            )}
          </div>
        )}

        <div className="overflow-y-auto px-5 sm:px-6 py-5 flex-1">{children}</div>

        {footer && (
          <div className="border-t border-[var(--border)] px-5 sm:px-6 py-4 flex items-center justify-end gap-2">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
