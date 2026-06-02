import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from './test/server'
import { useAppStore } from './store/useAppStore'
import App from './App'

describe('App auth bootstrap', () => {
  beforeEach(() => {
    useAppStore.setState({ user: null, authReady: false })
    window.history.pushState({}, '', '/')
  })

  it('redirects to the login page when /auth/me returns 401', async () => {
    server.use(
      http.get('/api/v1/auth/me', () => HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })),
    )
    render(<App />)
    expect(await screen.findByText('Sign in to sort statement activity.')).toBeInTheDocument()
  })

  it('renders the authenticated shell when /auth/me returns a user', async () => {
    // Default handlers return mockUser for /auth/me and seed settings/dashboard.
    render(<App />)
    expect(await screen.findByRole('navigation', { name: 'Primary' })).toBeInTheDocument()
    expect(screen.queryByText('Sign in to sort statement activity.')).toBeNull()
  })
})
