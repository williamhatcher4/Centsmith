import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from './ThemeProvider'
import { useTheme } from './theme'

function Probe() {
  const { accent, setAccent } = useTheme()
  return (
    <>
      <span data-testid="accent">{accent}</span>
      <button onClick={() => setAccent('violet')}>violet</button>
      <button onClick={() => setAccent('indigo')}>indigo</button>
    </>
  )
}

describe('ThemeProvider accent', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-accent')
  })

  it('defaults to indigo with no data-accent attribute', () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('accent')).toHaveTextContent('indigo')
    expect(document.documentElement.hasAttribute('data-accent')).toBe(false)
  })

  it('sets the data-accent attribute and persists the choice', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    await user.click(screen.getByText('violet'))
    expect(document.documentElement.getAttribute('data-accent')).toBe('violet')
    expect(localStorage.getItem('asset-tracker:accent')).toBe('violet')

    // Returning to indigo clears the attribute (baseline ships unchanged).
    await user.click(screen.getByText('indigo'))
    expect(document.documentElement.hasAttribute('data-accent')).toBe(false)
    expect(localStorage.getItem('asset-tracker:accent')).toBe('indigo')
  })

  it('restores a persisted accent on mount', () => {
    localStorage.setItem('asset-tracker:accent', 'emerald')
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId('accent')).toHaveTextContent('emerald')
    expect(document.documentElement.getAttribute('data-accent')).toBe('emerald')
  })
})
