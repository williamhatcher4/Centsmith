/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertCircle, CheckCircle, Info, X } from 'lucide-react'
import { cn } from '../../utils/cn'

export interface ToastAction {
  label: string
  onClick: () => void
}

interface Toast {
  id: string
  message: string
  type: 'success' | 'error' | 'info'
  action?: ToastAction
}

export interface ToastContextValue {
  success: (message: string, opts?: { action?: ToastAction }) => void
  error: (message: string, opts?: { action?: ToastAction }) => void
  info: (message: string, opts?: { action?: ToastAction }) => void
}

export const ToastContext = createContext<ToastContextValue>({
  success: () => {},
  error: () => {},
  info: () => {},
})

export function useToast(): ToastContextValue {
  return useContext(ToastContext)
}

const ICONS = {
  success: <CheckCircle className="size-4 shrink-0 text-[var(--success)]" />,
  error: <AlertCircle className="size-4 shrink-0 text-[var(--danger)]" />,
  info: <Info className="size-4 shrink-0 text-[var(--accent)]" />,
}

const ACCENTS: Record<Toast['type'], string> = {
  success: 'var(--success)',
  error: 'var(--danger)',
  info: 'var(--accent)',
}

const AUTO_DISMISS_MS = 6000

interface TimerState {
  handle: ReturnType<typeof setTimeout>
  remaining: number
  startedAt: number
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timers = useRef<Map<string, TimerState>>(new Map())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer.handle)
      timers.current.delete(id)
    }
  }, [])

  const add = useCallback(
    (type: Toast['type'], message: string, opts?: { action?: ToastAction }) => {
      const id = crypto.randomUUID()
      setToasts((prev) => [...prev, { id, message, type, action: opts?.action }])
      const handle = setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
      timers.current.set(id, { handle, remaining: AUTO_DISMISS_MS, startedAt: Date.now() })
    },
    [dismiss],
  )

  // Sonner edge-case: pause auto-dismiss while the tab is hidden, resume on return.
  useEffect(() => {
    const onVisibility = () => {
      if (document.hidden) {
        timers.current.forEach((timer, id) => {
          clearTimeout(timer.handle)
          const elapsed = Date.now() - timer.startedAt
          timers.current.set(id, { ...timer, remaining: Math.max(0, timer.remaining - elapsed) })
        })
      } else {
        timers.current.forEach((timer, id) => {
          const handle = setTimeout(() => dismiss(id), timer.remaining)
          timers.current.set(id, { handle, remaining: timer.remaining, startedAt: Date.now() })
        })
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [dismiss])

  const ctx: ToastContextValue = {
    success: (msg, opts) => add('success', msg, opts),
    error: (msg, opts) => add('error', msg, opts),
    info: (msg, opts) => add('info', msg, opts),
  }

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="fixed bottom-20 right-4 z-[200] flex flex-col items-end gap-2 pointer-events-none sm:bottom-4"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cn(
              'relative flex max-w-sm items-center gap-3 overflow-hidden rounded-[var(--radius-md)] py-3 pl-4 pr-3 pointer-events-auto',
              'bg-[var(--surface-strong)] backdrop-blur-xl backdrop-saturate-150',
              'border border-[var(--border-strong)] shadow-[var(--shadow-lg)]',
              'text-sm text-[var(--text)]',
              'animate-[slideUp_260ms_var(--ease-drawer)]',
            )}
          >
            <span
              aria-hidden="true"
              className="absolute inset-y-0 left-0 w-1"
              style={{ background: ACCENTS[toast.type] }}
            />
            {ICONS[toast.type]}
            <span className="min-w-0 flex-1">{toast.message}</span>
            {toast.action && (
              <button
                onClick={() => {
                  toast.action!.onClick()
                  dismiss(toast.id)
                }}
                className="ml-1 shrink-0 font-semibold text-[var(--accent)] hover:underline"
              >
                {toast.action.label}
              </button>
            )}
            <button
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss notification"
              className="ml-1 shrink-0 text-[var(--text-subtle)] transition-colors hover:text-[var(--text)]"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
