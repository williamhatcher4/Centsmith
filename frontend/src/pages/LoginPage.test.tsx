import { describe, expect, it } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../test/server'
import { renderWithProviders } from '../test/renderWithProviders'
import { LoginPage } from './LoginPage'
import { useAppStore } from '../store/useAppStore'

describe('LoginPage', () => {
  it('submits credentials and updates the app store on success', async () => {
    useAppStore.setState({ user: null, authReady: false })
    let submitted: URLSearchParams | null = null
    server.use(
      http.post('/api/v1/auth/login', async ({ request }) => {
        submitted = new URLSearchParams(await request.text())
        return HttpResponse.json({ message: 'Logged in', user: { id: 1, username: 'user1', display_name: 'User 1' } })
      }),
    )

    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)

    await user.type(screen.getByLabelText('Username'), 'user1')
    await user.type(screen.getByLabelText('Password'), 'secret')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(useAppStore.getState().user?.username).toBe('user1'))
    expect(submitted!.get('username')).toBe('user1')
    expect(submitted!.get('password')).toBe('secret')
  })

  it('shows an error message when the API rejects the login', async () => {
    server.use(
      http.post('/api/v1/auth/login', () =>
        HttpResponse.json({ detail: 'Incorrect username or password' }, { status: 401 }),
      ),
    )

    const user = userEvent.setup()
    renderWithProviders(<LoginPage />)
    await user.type(screen.getByLabelText('Username'), 'wrong')
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect username or password')
  })
})
