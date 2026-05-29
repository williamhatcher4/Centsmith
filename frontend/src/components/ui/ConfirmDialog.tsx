/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react'
import { Modal } from './Modal'
import { Button } from './Button'

export interface ConfirmOptions {
  title: string
  message: string
  confirmLabel?: string
  destructive?: boolean
}

interface ConfirmContextValue {
  confirm: (opts: ConfirmOptions) => Promise<boolean>
}

const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: () => Promise.resolve(false),
})

export function useConfirm(): (opts: ConfirmOptions) => Promise<boolean> {
  return useContext(ConfirmContext).confirm
}

interface DialogState extends ConfirmOptions {
  resolve: (value: boolean) => void
}

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<DialogState | null>(null)
  const resolveRef = useRef<((value: boolean) => void) | null>(null)

  const confirm = useCallback((opts: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve
      setState({ ...opts, resolve })
    })
  }, [])

  const close = useCallback((result: boolean) => {
    resolveRef.current?.(result)
    resolveRef.current = null
    setState(null)
  }, [])

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state && (
        <Modal
          open
          onClose={() => close(false)}
          title={state.title}
          size="sm"
          footer={
            <>
              <Button variant="ghost" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button
                variant={state.destructive ? 'danger' : 'primary'}
                onClick={() => close(true)}
              >
                {state.confirmLabel ?? 'Confirm'}
              </Button>
            </>
          }
        >
          <p className="text-sm text-[var(--text-subtle)]">{state.message}</p>
        </Modal>
      )}
    </ConfirmContext.Provider>
  )
}
