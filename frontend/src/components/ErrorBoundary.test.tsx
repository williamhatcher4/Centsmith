import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ErrorBoundary } from './ErrorBoundary'

function Bomb({ explode }: { explode: boolean }) {
  if (explode) throw new Error('test explosion')
  return <p>All good</p>
}

describe('ErrorBoundary', () => {
  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <Bomb explode={false} />
      </ErrorBoundary>,
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('renders the fallback UI when a child throws', () => {
    // Suppress console.error for the expected render error
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Bomb explode={true} />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
    spy.mockRestore()
  })

  it('the reload button is present in the fallback', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const reloadSpy = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload: reloadSpy },
      writable: true,
    })
    const user = userEvent.setup()
    render(
      <ErrorBoundary>
        <Bomb explode={true} />
      </ErrorBoundary>,
    )
    await user.click(screen.getByRole('button', { name: /reload/i }))
    expect(reloadSpy).toHaveBeenCalledOnce()
    spy.mockRestore()
  })
})
