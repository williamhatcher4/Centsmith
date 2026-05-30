import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useLocation } from 'react-router-dom'
import { renderWithProviders } from '../test/renderWithProviders'
import { CommandPalette } from './CommandPalette'
import { NAV_LINKS } from '../constants/nav'

function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="loc">{loc.pathname + loc.search}</div>
}

function Harness({ onLogout = () => {} }: { onLogout?: () => void }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      {open && <CommandPalette onClose={() => setOpen(false)} links={NAV_LINKS} onLogout={onLogout} />}
      <LocationProbe />
    </>
  )
}

describe('CommandPalette', () => {
  it('lists navigation commands and filters by query', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Harness />)

    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Dashboard/ })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Search pages and actions'), 'spend')
    expect(screen.getByRole('button', { name: /Spending/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Dashboard/ })).not.toBeInTheDocument()
  })

  it('navigates to the highlighted command on Enter', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Harness />)

    const input = screen.getByLabelText('Search pages and actions')
    await user.type(input, 'spending')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(screen.getByTestId('loc')).toHaveTextContent('/spending'))
  })

  it('runs the sign-out action', async () => {
    const onLogout = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<Harness onLogout={onLogout} />)

    await user.type(screen.getByLabelText('Search pages and actions'), 'sign out')
    await user.keyboard('{Enter}')
    expect(onLogout).toHaveBeenCalledTimes(1)
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Harness />)
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeInTheDocument()
    await user.click(screen.getByLabelText('Search pages and actions'))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Command palette' })).not.toBeInTheDocument())
  })
})
