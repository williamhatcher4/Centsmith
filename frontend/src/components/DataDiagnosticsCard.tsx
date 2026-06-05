import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FolderOpen, Upload } from 'lucide-react'
import { maintenanceApi } from '../api/maintenance'
import { Button, Card, CardHeader } from './ui'
import { useConfirm } from './ui/confirm-context'
import { useToast } from './ui/toast-context'

/** Compact human-readable file size (B / KB / MB). */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(1)} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

export function DataDiagnosticsCard() {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const restoreRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const { data: backups = [] } = useQuery({
    queryKey: ['maintenance', 'backups'],
    queryFn: maintenanceApi.listBackups,
  })

  async function run(label: string, fn: () => Promise<void>) {
    setBusy(label)
    try {
      await fn()
    } catch (err) {
      toast.error((err as Error).message)
    } finally {
      setBusy(null)
    }
  }

  function backup() {
    run('backup', async () => {
      const { path } = await maintenanceApi.downloadBackup()
      if (path) {
        await qc.invalidateQueries({ queryKey: ['maintenance', 'backups'] })
        toast.success(`Backup saved to ${path}`, {
          action: { label: 'Open folder', onClick: () => void maintenanceApi.openDataFolder() },
        })
      } else {
        toast.success('Backup downloaded.')
      }
    })
  }

  function openFolder() {
    run('folder', async () => {
      const { opened, path } = await maintenanceApi.openDataFolder()
      if (!opened) toast.info(`Your data is stored at: ${path}`)
    })
  }

  /** Shared destructive-restore flow: confirm, run, invalidate, offer reload. */
  async function confirmAndRestore(label: string, message: string, doRestore: () => Promise<{ message?: string }>) {
    const ok = await confirm({ title: 'Restore from backup', message, confirmLabel: 'Restore', destructive: true })
    if (!ok) return
    await run(label, async () => {
      const result = await doRestore()
      await qc.invalidateQueries()
      toast.success(result.message ?? 'Data restored.', {
        action: { label: 'Reload now', onClick: () => window.location.reload() },
      })
    })
  }

  function onRestoreFile(file: File) {
    return confirmAndRestore(
      'restore',
      'This replaces ALL current data with the contents of the backup file. This cannot be undone. Continue?',
      () => maintenanceApi.restore(file),
    )
  }

  function restoreFromDisk(name: string) {
    return confirmAndRestore(
      `restore:${name}`,
      `This replaces ALL current data with "${name}". This cannot be undone. Continue?`,
      () => maintenanceApi.restoreFromDisk(name),
    )
  }

  return (
    <Card padding="md" className="mb-6">
      <CardHeader
        title="Data & diagnostics"
        subtitle="Back up or restore your local database."
      />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" leftIcon={<Download className="size-4" />} onClick={backup} loading={busy === 'backup'}>
          Back up data
        </Button>
        <Button variant="secondary" leftIcon={<Upload className="size-4" />} onClick={() => restoreRef.current?.click()} loading={busy === 'restore'}>
          Restore from a file
        </Button>
        <Button variant="secondary" leftIcon={<FolderOpen className="size-4" />} onClick={openFolder} loading={busy === 'folder'}>
          Open data folder
        </Button>
      </div>

      {backups.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-sm font-medium text-[var(--text)]">Restore from a local backup</h3>
          <ul className="divide-y divide-[var(--border)] overflow-hidden rounded-md border border-[var(--border)]">
            {backups.map((b) => (
              <li key={b.name} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm text-[var(--text)]">{b.name}</p>
                  <p className="text-xs text-[var(--text-subtle)]">
                    {formatBytes(b.size_bytes)} · {new Date(b.modified).toLocaleString()}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => restoreFromDisk(b.name)}
                  loading={busy === `restore:${b.name}`}
                >
                  Restore
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <input
        ref={restoreRef}
        type="file"
        accept=".db,.sqlite,application/x-sqlite3"
        aria-label="Restore backup file"
        className="hidden"
        onChange={(e) => {
          const picked = e.target.files?.[0]
          if (picked) onRestoreFile(picked)
          if (restoreRef.current) restoreRef.current.value = ''
        }}
      />
    </Card>
  )
}
