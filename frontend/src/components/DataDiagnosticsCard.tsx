import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Download, FolderOpen, LifeBuoy, Upload } from 'lucide-react'
import { maintenanceApi } from '../api/maintenance'
import { Button, Card, CardHeader } from './ui'
import { useConfirm } from './ui/confirm-context'
import { useToast } from './ui/toast-context'

export function DataDiagnosticsCard() {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const restoreRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState<string | null>(null)

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
      await maintenanceApi.downloadBackup()
      toast.success('Backup downloaded.')
    })
  }

  function supportBundle() {
    run('support', async () => {
      await maintenanceApi.downloadSupportBundle()
      toast.success('Support bundle downloaded. It excludes your transactions and any secrets.')
    })
  }

  function openFolder() {
    run('folder', async () => {
      const { opened, path } = await maintenanceApi.openDataFolder()
      if (!opened) toast.info(`Your data is stored at: ${path}`)
    })
  }

  async function onRestoreFile(file: File) {
    const ok = await confirm({
      title: 'Restore from backup',
      message: 'This replaces ALL current data with the contents of the backup file. This cannot be undone. Continue?',
      confirmLabel: 'Restore',
      destructive: true,
    })
    if (!ok) return
    await run('restore', async () => {
      const result = await maintenanceApi.restore(file)
      await qc.invalidateQueries()
      toast.success(result.message ?? 'Data restored.', {
        action: { label: 'Reload now', onClick: () => window.location.reload() },
      })
    })
  }

  return (
    <Card padding="md" className="mb-6">
      <CardHeader
        title="Data & diagnostics"
        subtitle="Back up or restore your local database, or share a diagnostics bundle with support."
      />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" leftIcon={<Download className="size-4" />} onClick={backup} loading={busy === 'backup'}>
          Back up data
        </Button>
        <Button variant="secondary" leftIcon={<Upload className="size-4" />} onClick={() => restoreRef.current?.click()} loading={busy === 'restore'}>
          Restore from backup
        </Button>
        <Button variant="secondary" leftIcon={<FolderOpen className="size-4" />} onClick={openFolder} loading={busy === 'folder'}>
          Open data folder
        </Button>
        <Button variant="secondary" leftIcon={<LifeBuoy className="size-4" />} onClick={supportBundle} loading={busy === 'support'}>
          Download support bundle
        </Button>
      </div>
      <p className="mt-3 text-xs text-[var(--text-subtle)]">
        The support bundle includes app version, OS, and recent logs. It never includes your transactions, passwords, or tokens.
      </p>
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
