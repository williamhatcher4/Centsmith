import { useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Upload } from 'lucide-react'
import { transactionsApi } from '../api/transactions'
import type { ImportPreview } from '../types'
import { cn } from '../utils/cn'
import { Badge, Button, Modal } from './ui'
import { repeatGroupInfo, signedMoney } from './ImportModal.helpers'

type ImportMode = 'card' | 'checking'

export function ImportModal({ onClose, mode = 'card' }: { onClose: () => void; mode?: ImportMode }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<{ imported: number; skipped: number; ignored_credits: number; skipped_errors: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)

  const isChecking = mode === 'checking'
  const step = result ? 'done' : preview ? 'preview' : 'upload'
  const repeatInfo = useMemo(() => repeatGroupInfo(preview?.rows ?? []), [preview])
  const titles = {
    upload: isChecking ? 'Import checking statement' : 'Import statement',
    preview: isChecking ? 'Checking import preview' : 'Import preview',
    done: 'Import complete',
  }
  const uploadCopy = isChecking
    ? 'Drop a checking-account statement. Every row (deposits and withdrawals) becomes a Personal transaction in your inbox.'
    : 'Drop a credit card statement. This app supports the headerless account activity CSV and American Express XLS formats you provided.'
  const errorsCopy = result && result.skipped_errors > 0 ? ` ${result.skipped_errors} row${result.skipped_errors === 1 ? '' : 's'} could not be parsed and were skipped.` : ''
  const doneCopy = isChecking
    ? `${result?.skipped ?? 0} duplicates skipped.${errorsCopy} New transactions are waiting in the Personal Inbox.`
    : `${result?.skipped ?? 0} duplicates skipped. ${result?.ignored_credits ?? 0} credit transactions ignored.${errorsCopy} New spending is waiting in the Inbox.`

  async function readFile(nextFile: File) {
    setFile(nextFile)
    setError('')
    setLoading(true)
    try {
      const preview = isChecking
        ? await transactionsApi.previewCheckingImport(nextFile)
        : await transactionsApi.previewImport(nextFile)
      setPreview(preview)
    } catch (err) {
      setError((err as Error).message)
      setFile(null)
    } finally {
      setLoading(false)
    }
  }

  async function confirm() {
    if (!file) return
    setLoading(true)
    setError('')
    try {
      const next = isChecking
        ? await transactionsApi.confirmCheckingImport(file)
        : await transactionsApi.confirmImport(file)
      setResult(next)
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
      qc.invalidateQueries({ queryKey: ['income'] })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setFile(null)
    setPreview(null)
    setResult(null)
    setError('')
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <Modal open onClose={onClose} title={titles[step]} size="xl" footer={step === 'preview' && preview ? <><Button variant="secondary" leftIcon={<ArrowLeft className="size-4" />} onClick={reset}>Back</Button><Button onClick={confirm} loading={loading} disabled={preview.to_import === 0}>Import {preview.to_import}</Button></> : step === 'done' ? <Button onClick={onClose}>Done</Button> : <Button variant="secondary" onClick={onClose}>Cancel</Button>}>
      {step === 'upload' && (
        <div>
          <p className="mb-5 text-sm leading-relaxed text-[var(--text-muted)]">{uploadCopy}</p>
          <button type="button" onClick={() => fileRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setDragOver(true) }} onDragLeave={() => setDragOver(false)} onDrop={(e) => { e.preventDefault(); setDragOver(false); const dropped = e.dataTransfer.files[0]; if (dropped) readFile(dropped) }} className={cn('flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-[8px] border-2 border-dashed px-6 py-10 text-sm transition-colors', dragOver ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]' : 'border-[var(--border-strong)] bg-[var(--surface-muted)] text-[var(--text-subtle)] hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]')}>
            {loading ? <><span className="size-6 animate-spin rounded-full border-2 border-current border-r-transparent" /><span>Parsing file...</span></> : <><Upload className="size-7" /><span><strong className="text-[var(--text)]">Choose file</strong> or drag and drop CSV/XLS</span></>}
          </button>
          <input ref={fileRef} type="file" accept=".csv,.xls,text/csv,application/vnd.ms-excel" className="hidden" onChange={(e) => { const picked = e.target.files?.[0]; if (picked) readFile(picked) }} />
          {error && <div role="alert" className="mt-3 rounded-[8px] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)]">{error}</div>}
        </div>
      )}
      {step === 'preview' && preview && (
        <div>
          <div className={cn('mb-4 grid gap-3 rounded-[8px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3', isChecking ? 'sm:grid-cols-4' : 'sm:grid-cols-5')}>
            <div><div className="text-[11px] uppercase text-[var(--text-faint)]">Format</div><div className="font-semibold">{preview.statement_format}</div></div>
            <div><div className="text-[11px] uppercase text-[var(--text-faint)]">To import</div><div className="font-semibold text-[var(--success)]">{preview.to_import}</div></div>
            <div><div className="text-[11px] uppercase text-[var(--text-faint)]">Duplicates</div><div className="font-semibold text-[var(--text-subtle)]">{preview.duplicates}</div></div>
            {!isChecking && <div><div className="text-[11px] uppercase text-[var(--text-faint)]">Credits ignored</div><div className="font-semibold text-[var(--text-subtle)]">{preview.ignored_credits}</div></div>}
            <div><div className="text-[11px] uppercase text-[var(--text-faint)]">Rows</div><div className="font-semibold">{preview.total}</div></div>
            {preview.skipped_errors > 0 && <div><div className="text-[11px] uppercase text-[var(--text-faint)]">Skipped</div><div className="font-semibold text-[var(--danger)]">{preview.skipped_errors}</div></div>}
          </div>
          <div className="max-h-[420px] overflow-auto rounded-[8px] border border-[var(--border)]">
            <table className="w-full text-sm"><thead className="sticky top-0 bg-[var(--surface-solid)]"><tr className="border-b border-[var(--border)] text-left text-[11px] uppercase text-[var(--text-subtle)]"><th className="px-3 py-2">Date</th><th className="px-3 py-2">Description</th><th className="px-3 py-2 text-right">Amount</th><th className="px-3 py-2">Status</th></tr></thead><tbody>
              {preview.rows.map((row) => { const repeat = repeatInfo.get(row.row_number); return <tr key={row.row_number} className={cn('border-b border-[var(--border)] last:border-0', row.is_duplicate && 'opacity-50')}><td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--text-subtle)]">{row.date}</td><td className="max-w-[260px] truncate px-3 py-2 font-medium">{row.description}</td><td className={cn('whitespace-nowrap px-3 py-2 text-right font-bold tabular-nums', row.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>{signedMoney(row.amount_cents, row.transaction_type)}</td><td className="px-3 py-2"><div className="flex flex-wrap items-center gap-1.5">{row.is_duplicate ? <Badge tone="muted">duplicate</Badge> : <Badge tone="success">new</Badge>}{repeat && <Badge tone="muted">repeat in file ({repeat.index} of {repeat.size})</Badge>}</div></td></tr> })}
            </tbody></table>
          </div>
          {error && <div role="alert" className="mt-3 rounded-[8px] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)]">{error}</div>}
        </div>
      )}
      {step === 'done' && result && <div className="py-4 text-center"><div className="mx-auto mb-3 flex size-14 items-center justify-center rounded-full bg-[var(--success-soft)] text-[var(--success)]"><CheckCircle2 className="size-8" /></div><p className="text-xl font-bold">{result.imported} transactions imported</p><p className="mt-1 text-sm text-[var(--text-subtle)]">{doneCopy}</p></div>}
    </Modal>
  )
}
