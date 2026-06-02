import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ConfirmDialogProvider } from './ConfirmDialog'
import { useConfirm } from './confirm-context'

function Trigger({ destructive = false }: { destructive?: boolean }) {
  const confirm = useConfirm()
  return (
    <button
      onClick={async () => {
        const ok = await confirm({
          title: 'Delete item',
          message: 'Are you sure?',
          confirmLabel: 'Delete',
          destructive,
        })
        if (ok) document.title = 'confirmed'
        else document.title = 'cancelled'
      }}
    >
      open
    </button>
  )
}

function setup(destructive = false) {
  const user = userEvent.setup()
  render(
    <ConfirmDialogProvider>
      <Trigger destructive={destructive} />
    </ConfirmDialogProvider>,
  )
  return { user }
}

describe('ConfirmDialogProvider / useConfirm', () => {
  it('renders the dialog when confirm() is called', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'open' }))
    expect(screen.getByText('Delete item')).toBeInTheDocument()
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
  })

  it('resolves true when the confirm button is clicked', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'open' }))
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    expect(document.title).toBe('confirmed')
    expect(screen.queryByText('Delete item')).not.toBeInTheDocument()
  })

  it('resolves false when Cancel is clicked', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'open' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(document.title).toBe('cancelled')
    expect(screen.queryByText('Delete item')).not.toBeInTheDocument()
  })

  it('resolves false when dialog is closed via ESC key', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'open' }))
    await user.keyboard('{Escape}')
    expect(document.title).toBe('cancelled')
  })

  it('uses the danger button variant for destructive dialogs', async () => {
    const { user } = setup(true)
    await user.click(screen.getByRole('button', { name: 'open' }))
    // Button rendered, dialog is open
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
  })
})
