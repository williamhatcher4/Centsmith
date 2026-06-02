import { Download, Trash2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { importsApi } from '../api/imports'
import type { ImportBatch } from '../types'
import { Badge, Button, Card, CardHeader, IconButton, PageHeader, useConfirm, useToast } from '../components/ui'

function formatImportedAt(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function ImportsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const confirm = useConfirm()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['imports'],
    queryFn: () => importsApi.list(),
  })

  const deleteMutation = useMutation({
    mutationFn: (batch: ImportBatch) => importsApi.deleteBatch(batch.id),
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['imports'] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
      qc.invalidateQueries({ queryKey: ['income'] })
      toast.success(`Removed ${result.removed_rows} transaction${result.removed_rows === 1 ? '' : 's'}.`)
    },
    onError: (err: Error) => toast.error(err.message || 'Undo failed'),
  })

  async function handleDelete(batch: ImportBatch) {
    const classifiedNote = batch.row_count > 0
      ? ` You've classified or categorized some of these rows; that work will be lost.`
      : ''
    const ok = await confirm({
      title: 'Undo this import?',
      message: `This will permanently delete the ${batch.row_count} transaction${batch.row_count === 1 ? '' : 's'} from "${batch.filename}".${classifiedNote}`,
      confirmLabel: 'Undo import',
      destructive: true,
    })
    if (!ok) return
    deleteMutation.mutate(batch)
  }

  return (
    <Card padding="md">
      <CardHeader title="Past imports" subtitle="Undo a previous import to remove every row it created" />
      {isLoading && <p className="text-sm text-[var(--text-subtle)]">Loading…</p>}
      {isError && <p className="text-sm text-[var(--danger)]">Could not load import history.</p>}
      {data && data.length === 0 && (
        <p className="text-sm text-[var(--text-subtle)]">No imports yet. Import a statement from the Inbox.</p>
      )}
      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border-strong)] bg-[var(--surface-muted)] text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--text-subtle)]">
                <th className="px-3 py-2">When</th>
                <th className="px-3 py-2">Filename</th>
                <th className="px-3 py-2">Format</th>
                <th className="px-3 py-2 text-right">Rows</th>
                <th className="px-3 py-2"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((batch) => (
                <tr key={batch.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="whitespace-nowrap px-3 py-2 text-[var(--text-subtle)]">{formatImportedAt(batch.imported_at)}</td>
                  <td className="max-w-[260px] truncate px-3 py-2 font-medium">{batch.filename}</td>
                  <td className="px-3 py-2">
                    {batch.statement_format ? <Badge tone="muted">{batch.statement_format}</Badge> : <span className="text-[var(--text-faint)]">—</span>}
                    {batch.created_by_action === 'legacy' && <Badge tone="muted">legacy</Badge>}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">{batch.row_count}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <IconButton
                      aria-label={`Undo import ${batch.filename}`}
                      variant="danger"
                      onClick={() => handleDelete(batch)}
                      disabled={deleteMutation.isPending}
                      icon={<Trash2 className="size-4" />}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

export function ExportsPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Data" title="Exports" subtitle="Download Personal and Work transactions as separate CSV files" />
      <div className="grid gap-4 md:grid-cols-2">
        <Card padding="md">
          <CardHeader title="Personal transactions" subtitle="Only rows sorted as Personal" />
          <Button leftIcon={<Download className="size-4" />}>
            <a href="/api/v1/transactions/export/personal" className="text-inherit no-underline">Download Personal CSV</a>
          </Button>
        </Card>
        <Card padding="md">
          <CardHeader title="Work transactions" subtitle="Only rows sorted as Work" />
          <Button leftIcon={<Download className="size-4" />}>
            <a href="/api/v1/transactions/export/work" className="text-inherit no-underline">Download Work CSV</a>
          </Button>
        </Card>
      </div>
      <ImportsSection />
    </div>
  )
}
