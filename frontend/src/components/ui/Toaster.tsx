import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
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
  success: <CheckCircle className="size-4 text-green-500 shrink-0" />,
  error: <AlertCircle className="size-4 text-red-500 shrink-0" />,
  info: <Info className="size-4 text-blue-500 shrink-0" />,
}

const AUTO_DISMISS_MS = 6000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const timerRefs = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
    const timer = timerRefs.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timerRefs.current.delete(id)
    }
  }, [])

  const add = useCallback(
    (type: Toast['type'], message: string, opts?: { action?: ToastAction }) => {
      const id = crypto.randomUUID()
      setToasts((prev) => [...prev, { id, message, type, action: opts?.action }])
      const timer = setTimeout(() => dismiss(id), AUTO_DISMISS_MS)
      timerRefs.current.set(id, timer)
    },
    [dismiss],
  )

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
        className="fixed bottom-20 sm:bottom-4 right-4 z-[200] flex flex-col gap-2 items-end pointer-events-none"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={cn(
              'flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg max-w-sm pointer-events-auto',
              'bg-[var(--surface-strong)] border border-[var(--border-strong)]',
              'text-sm text-[var(--text)]',
              'animate-[slideUp_220ms_cubic-bezier(0.16,1,0.3,1)]',
            )}
          >
            {ICONS[toast.type]}
            <span className="flex-1 min-w-0">{toast.message}</span>
            {toast.action && (
              <button
                onClick={() => {
                  toast.action!.onClick()
                  dismiss(toast.id)
                }}
                className="text-[var(--accent)] font-semibold hover:underline shrink-0 ml-1"
              >
                {toast.action.label}
              </button>
            )}
            <button
              onClick={() => dismiss(toast.id)}
              aria-label="Dismiss notification"
              className="text-[var(--text-subtle)] hover:text-[var(--text)] shrink-0 ml-1"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
