import { createContext, use } from 'react'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  destructive?: boolean
}

export interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions) => Promise<boolean>
}

export const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: () => Promise.resolve(false),
})

export function useConfirm(): (opts: ConfirmOptions) => Promise<boolean> {
  return use(ConfirmContext).confirm
}
