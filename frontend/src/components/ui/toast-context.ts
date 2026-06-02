import { createContext, use } from 'react'

export interface ToastAction {
  label: string
  onClick: () => void
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
  return use(ToastContext)
}
