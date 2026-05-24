import { Navigate } from 'react-router-dom'
import { useAppStore } from '../store/useAppStore'

export function PrivateRoute({ children }: { children: React.ReactNode }) {
  const user = useAppStore((s) => s.user)
  const authReady = useAppStore((s) => s.authReady)
  if (!authReady) return null
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

