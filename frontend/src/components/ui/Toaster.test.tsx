import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ToastProvider } from './Toaster'
import { useToast } from './toast-context'

function ToastTrigger() {
  const toast = useToast()
  return (
    <div>
      <button onClick={() => toast.success('Saved!')}>success</button>
      <button onClick={() => toast.error('Failed!')}>error</button>
      <button onClick={() => toast.info('Heads up!')}>info</button>
      <button
        onClick={() =>
          toast.success('Imported', {
            action: { label: 'Undo', onClick: vi.fn() },
          })
        }
      >
        with-action
      </button>
    </div>
  )
}

function setup() {
  const user = userEvent.setup()
  render(
    <ToastProvider>
      <ToastTrigger />
    </ToastProvider>,
  )
  return { user }
}

describe('ToastProvider / useToast', () => {
  it('renders a success toast', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'success' }))
    expect(screen.getByText('Saved!')).toBeInTheDocument()
  })

  it('renders an error toast', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'error' }))
    expect(screen.getByText('Failed!')).toBeInTheDocument()
  })

  it('renders an info toast', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'info' }))
    expect(screen.getByText('Heads up!')).toBeInTheDocument()
  })

  it('renders the action button on toasts that have one', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'with-action' }))
    expect(screen.getByText('Imported')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument()
  })

  it('dismisses the toast when the dismiss button is clicked', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'success' }))
    expect(screen.getByText('Saved!')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Dismiss notification' }))
    expect(screen.queryByText('Saved!')).not.toBeInTheDocument()
  })

  it('dismisses the toast when the action button is clicked', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'with-action' }))
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(screen.queryByText('Imported')).not.toBeInTheDocument()
  })

  it('auto-dismisses after timeout', () => {
    vi.useFakeTimers()
    render(<ToastProvider><ToastTrigger /></ToastProvider>)
    // Use fireEvent (synchronous) to avoid timer conflicts with userEvent internals
    fireEvent.click(screen.getByRole('button', { name: 'success' }))
    expect(screen.getByText('Saved!')).toBeInTheDocument()
    act(() => { vi.advanceTimersByTime(6001) })
    expect(screen.queryByText('Saved!')).not.toBeInTheDocument()
    vi.useRealTimers()
  })
})
