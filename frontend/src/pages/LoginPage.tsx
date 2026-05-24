import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CreditCard } from 'lucide-react'
import { authApi } from '../api/auth'
import { useAppStore } from '../store/useAppStore'
import { Button, Card, Field, Input } from '../components/ui'

export function LoginPage() {
  const navigate = useNavigate()
  const setUser = useAppStore((s) => s.setUser)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await authApi.login(username, password)
      setUser(res.user)
      navigate('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <Card padding="lg" className="w-full max-w-[420px]">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex size-11 items-center justify-center rounded-[8px] bg-[var(--accent-soft)] text-[var(--accent)]"><CreditCard className="size-6" /></span>
          <div>
            <h1 className="text-xl font-bold text-[var(--text)]">Credit Tracker</h1>
            <p className="text-sm text-[var(--text-subtle)]">Sign in to sort statement activity.</p>
          </div>
        </div>
        <form onSubmit={submit}>
          <Field label="Username" htmlFor="username"><Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} /></Field>
          <Field label="Password" htmlFor="password"><Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
          {error && <div role="alert" className="mb-3 rounded-[8px] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)]">{error}</div>}
          <Button type="submit" className="w-full" loading={loading}>Sign in</Button>
        </form>
      </Card>
    </div>
  )
}
