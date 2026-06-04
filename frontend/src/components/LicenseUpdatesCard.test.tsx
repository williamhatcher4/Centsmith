import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../test/renderWithProviders'
import { LicenseUpdatesCard } from './LicenseUpdatesCard'

const invoke = vi.fn()

beforeEach(() => {
  invoke.mockReset()
  window.__TAURI__ = { core: { invoke } }
})

afterEach(() => {
  delete window.__TAURI__
})

describe('LicenseUpdatesCard', () => {
  it('shows the disabled state when no license is stored', async () => {
    invoke.mockResolvedValue({ present: false, hint: null })
    renderWithProviders(<LicenseUpdatesCard />)
    expect(await screen.findByText(/no license entered/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove/i })).not.toBeInTheDocument()
  })

  it('saves a pasted license and reflects the active status', async () => {
    invoke.mockImplementation((cmd: string) => {
      if (cmd === 'set_license_token') return Promise.resolve({ present: true, hint: '…WXYZ' })
      return Promise.resolve({ present: false, hint: null })
    })
    const user = userEvent.setup()
    renderWithProviders(<LicenseUpdatesCard />)
    await screen.findByText(/no license entered/i)

    await user.type(screen.getByLabelText(/license key/i), 'my-key-WXYZ')
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByText(/active license ending/i)).toBeInTheDocument()
    expect(screen.getByText('…WXYZ')).toBeInTheDocument()
    expect(invoke).toHaveBeenCalledWith('set_license_token', { token: 'my-key-WXYZ' })
  })

  it('does not call the backend when saving with an empty field', async () => {
    invoke.mockResolvedValue({ present: false, hint: null })
    const user = userEvent.setup()
    renderWithProviders(<LicenseUpdatesCard />)
    await screen.findByText(/no license entered/i)

    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByText(/paste your license key first/i)).toBeInTheDocument()
    expect(invoke).not.toHaveBeenCalledWith('set_license_token', expect.anything())
  })

  it('removes a stored license', async () => {
    invoke.mockImplementation((cmd: string) => {
      if (cmd === 'get_license_status') return Promise.resolve({ present: true, hint: '…WXYZ' })
      if (cmd === 'clear_license_token') return Promise.resolve({ present: false, hint: null })
      return Promise.resolve({ present: false, hint: null })
    })
    const user = userEvent.setup()
    renderWithProviders(<LicenseUpdatesCard />)
    expect(await screen.findByText(/active license ending/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /remove/i }))

    expect(await screen.findByText(/no license entered/i)).toBeInTheDocument()
    expect(invoke).toHaveBeenCalledWith('clear_license_token')
  })
})
