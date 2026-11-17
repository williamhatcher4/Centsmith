import { useEffect, useState } from 'react'
import { updatesApi, type UpdateCheckStatus } from '../api/updates'
import { relativeTimeFrom } from '../utils/relativeTime'
import { Card, CardHeader } from './ui'

/** One-line summary of the last update check ("5 minutes ago — Up to date"). */
function updateCheckSummary(status: UpdateCheckStatus): string {
  if (!status.present) return 'No update check has run yet.'
  const when = status.checked_at ? relativeTimeFrom(status.checked_at) : 'at an unknown time'
  const outcome =
    status.result === 'ok-uptodate' ? 'Up to date' :
    status.result === 'ok-update-available' ? 'Update available' :
    status.result === 'error' ? `Failed${status.detail ? `: ${status.detail}` : ''}` :
    'Unknown result'
  return `Last update check: ${when} — ${outcome}`
}

/**
 * Desktop-only card showing the status of automatic updates. Updates are free
 * and checked by the Rust shell on launch. Render only when `updatesApi.isDesktop()`.
 */
export function UpdatesCard() {
  const [updateCheck, setUpdateCheck] = useState<UpdateCheckStatus | null>(null)

  useEffect(() => {
    // Read failures just hide the status line.
    updatesApi
      .getUpdateStatus()
      .then(setUpdateCheck)
      .catch(() => setUpdateCheck(null))
  }, [])

  return (
    <Card padding="md" className="mb-6">
      <CardHeader
        title="Updates"
        subtitle="Centsmith is free. Updates are checked automatically when the app starts."
      />
      {updateCheck && (
        <p className="text-sm text-[var(--text-subtle)]">{updateCheckSummary(updateCheck)}</p>
      )}
    </Card>
  )
}
