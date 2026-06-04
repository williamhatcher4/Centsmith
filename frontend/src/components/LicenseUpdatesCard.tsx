import { useEffect, useState } from 'react'
import { KeyRound, Trash2 } from 'lucide-react'
import { licenseApi, type LicenseStatus } from '../api/license'
import { Button, Card, CardHeader, Field, Input } from './ui'
import { useToast } from './ui/toast-context'

/**
 * Desktop-only card for entering the paid update license. The token is stored
 * by the Rust shell and attached to update checks; without it, auto-update is
 * disabled (the app still runs fully). Render only when `licenseApi.isDesktop()`.
 */
export function LicenseUpdatesCard() {
  const toast = useToast()
  const [status, setStatus] = useState<LicenseStatus | null>(null)
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState<'save' | 'clear' | null>(null)

  useEffect(() => {
    licenseApi
      .getStatus()
      .then(setStatus)
      .catch(() => setStatus({ present: false, hint: null }))
  }, [])

  async function save() {
    const next = token.trim()
    if (!next) {
      toast.error('Paste your license key first.')
      return
    }
    setBusy('save')
    try {
      setStatus(await licenseApi.set(next))
      setToken('')
      toast.success('License saved. Updates are now enabled.')
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(null)
    }
  }

  async function clear() {
    setBusy('clear')
    try {
      setStatus(await licenseApi.clear())
      toast.success('License removed. Updates are disabled until you add one.')
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card padding="md" className="mb-6">
      <CardHeader
        title="License &amp; updates"
        subtitle="Enter the license key from your purchase to receive automatic updates."
      />
      <p className="mb-4 text-sm text-[var(--text-subtle)]">
        {status?.present ? (
          <>Active license ending <span className="font-mono">{status.hint}</span> — automatic updates are enabled.</>
        ) : (
          <>No license entered — automatic updates are disabled until you add one.</>
        )}
      </p>
      <Field label="License key" htmlFor="license-token">
        <div className="flex gap-2">
          <Input
            id="license-token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="Paste your license key"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                save()
              }
            }}
          />
          <Button leftIcon={<KeyRound className="size-4" />} onClick={save} loading={busy === 'save'}>
            Save
          </Button>
          {status?.present && (
            <Button
              variant="secondary"
              leftIcon={<Trash2 className="size-4" />}
              onClick={clear}
              loading={busy === 'clear'}
            >
              Remove
            </Button>
          )}
        </div>
      </Field>
    </Card>
  )
}
