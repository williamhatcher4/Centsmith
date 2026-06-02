import { describe, expect, it, beforeEach } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../test/renderWithProviders'
import { PrivateRoute } from './PrivateRoute'
import { useAppStore } from '../store/useAppStore'

function mountGuard(route = '/protected') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<div>LOGIN-PAGE</div>} />
      <Route
        path="/protected"
        element={
          <PrivateRoute>
            <div>PROTECTED-CONTENT</div>
          </PrivateRoute>
        }
      />
    </Routes>,
    { route },
  )
}

describe('PrivateRoute', () => {
  beforeEach(() => {
    useAppStore.setState({ user: null, authReady: false })
  })

  it('renders nothing while auth is not ready', () => {
    useAppStore.setState({ user: null, authReady: false })
    mountGuard()
    expect(screen.queryByText('PROTECTED-CONTENT')).toBeNull()
    expect(screen.queryByText('LOGIN-PAGE')).toBeNull()
  })

  it('redirects to /login when ready and unauthenticated', () => {
    useAppStore.setState({ user: null, authReady: true })
    mountGuard()
    expect(screen.getByText('LOGIN-PAGE')).toBeInTheDocument()
    expect(screen.queryByText('PROTECTED-CONTENT')).toBeNull()
  })

  it('renders children when ready and authenticated', () => {
    useAppStore.setState({
      user: { id: 1, username: 'user1', display_name: 'User 1' },
      authReady: true,
    })
    mountGuard()
    expect(screen.getByText('PROTECTED-CONTENT')).toBeInTheDocument()
    expect(screen.queryByText('LOGIN-PAGE')).toBeNull()
  })
})
