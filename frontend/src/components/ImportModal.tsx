import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, CheckCircle2, Upload } from 'lucide-react'
import { importsApi } from '../api/imports'
import { importProfilesApi } from '../api/importProfiles'
import { cardsApi } from '../api/cards'
import { transactionsApi } from '../api/transactions'
import type { ColumnMapping, ImportPreview, ImportResult } from '../types'
import { cn } from '../utils/cn'
import { invalidateAnalytics, invalidateLedger } from '../utils/queryInvalidation'
import { Badge, Button, Field, Modal, Select, useToast } from './ui'
import { defaultMappingDraft, draftToMapping, repeatGroupInfo, signedMoney, type MappingDraft } from './ImportModal.helpers'

type ImportMode = 'card' | 'checking'

function MappingStep({
  preview,
  loading,
  error,
  onApply,
}: {
  preview: ImportPreview
  loading: boolean
  error: string
  onApply: (mapping: ColumnMapping, draft: MappingDraft) => void
}) {
  const [draft, setDraft] = useState<MappingDraft>(() => defaultMappingDraft(preview))
  const columns = preview.available_columns
  const columnOptions = columns.map((label, idx) => ({ value: String(idx), label: label || `Column ${idx + 1}` }))
  const set = (patch: Partial<MappingDraft>) => setDraft((d) => ({ ...d, ...patch }))

  return (
    <div>
      <p className="mb-4 text-sm leading-relaxed text-[var(--text-muted)]">
        We couldn&rsquo;t recognize this file&rsquo;s columns automatically. Tell us which column is which and we&rsquo;ll import it.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Date column" htmlFor="map-date">
          <Select id="map-date" value={String(draft.date_column)} onChange={(e) => set({ date_column: Number(e.target.value) })}>
            {columnOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label="Description column" htmlFor="map-desc">
          <Select id="map-desc" value={String(draft.description_column)} onChange={(e) => set({ description_column: Number(e.target.value) })}>
            {columnOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </Field>
        <Field label="Amount style" htmlFor="map-mode">
          <Select id="map-mode" value={draft.amount_mode} onChange={(e) => set({ amount_mode: e.target.value as MappingDraft['amount_mode'] })}>
            <option value="single">Single amount column</option>
            <option value="split">Separate debit / credit columns</option>
          </Select>
        </Field>
        {draft.amount_mode === 'single' ? (
          <>
            <Field label="Amount column" htmlFor="map-amount">
              <Select id="map-amount" value={String(draft.amount_column)} onChange={(e) => set({ amount_column: Number(e.target.value) })}>
                {columnOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
            <Field label="Amount convention" htmlFor="map-convention">
              <Select id="map-convention" value={draft.amount_convention} onChange={(e) => set({ amount_convention: e.target.value as MappingDraft['amount_convention'] })}>
                <option value="signed">Already signed (+ income / − spending)</option>
                <option value="charges_positive">Charges are positive (AmEx-style)</option>
                <option value="charges_negative">Charges are negative</option>
              </Select>
            </Field>
          </>
        ) : (
          <>
            <Field label="Debit (out) column" htmlFor="map-debit">
              <Select id="map-debit" value={String(draft.debit_column)} onChange={(e) => set({ debit_column: Number(e.target.value) })}>
                {columnOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
            <Field label="Credit (in) column" htmlFor="map-credit">
              <Select id="map-credit" value={String(draft.credit_column)} onChange={(e) => set({ credit_column: Number(e.target.value) })}>
                {columnOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
            </Field>
          </>
        )}
      </div>
      {preview.sample_rows.length > 0 && (
        <div className="mt-4 max-h-[220px] overflow-auto rounded-[8px] border border-[var(--border)]">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[var(--surface-solid)]">
              <tr className="border-b border-[var(--border)] text-left text-[var(--text-subtle)]">
                {columns.map((label, idx) => <th key={idx} className="px-2 py-1.5 font-medium">{label || `Column ${idx + 1}`}</th>)}
              </tr>
            </thead>
            <tbody>
              {preview.sample_rows.slice(0, 5).map((row, r) => (
                <tr key={r} className="border-b border-[var(--border)] last:border-0">
                  {row.map((cell, c) => <td key={c} className="max-w-[160px] truncate px-2 py-1.5 text-[var(--text-subtle)]">{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {error && <div role="alert" className="mt-3 rounded-[8px] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)]">{error}</div>}
      <div className="mt-4 flex justify-end">
        <Button onClick={() => onApply(draftToMapping(draft), draft)} loading={loading}>Preview with this mapping</Button>
      </div>
    </div>
  )
}

function SkippedRowsDetails({ preview }: { preview: ImportPreview }) {
  const skipped = preview.skipped_rows ?? []
  if (skipped.length === 0) return null
  return (
    <details className="mt-4 rounded-[8px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3 text-sm">
      <summary className="cursor-pointer font-medium text-[var(--text)]">
        {preview.skipped_rows.length} row{preview.skipped_rows.length === 1 ? '' : 's'} skipped — see why
      </summary>
      <ul className="mt-3 flex flex-col gap-2">
        {skipped.map((s) => (
          <li key={s.row_number} className="flex flex-col gap-0.5 border-b border-[var(--border)] pb-2 last:border-0 last:pb-0">
            <span className="text-[var(--text)]"><span className="font-medium">Row {s.row_number}:</span> {s.message}</span>
            <span className="text-xs text-[var(--text-subtle)]">
              {[s.raw_date, s.raw_description, s.raw_amount].filter(Boolean).join(' · ') || '(empty row)'}
            </span>
          </li>
        ))}
      </ul>
    </details>
  )
}

export function ImportModal({ onClose, mode = 'card' }: { onClose: () => void; mode?: ImportMode }) {
  const qc = useQueryClient()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [chargesPositive, setChargesPositive] = useState<boolean | undefined>(undefined)
  const [dayFirst, setDayFirst] = useState<boolean | undefined>(undefined)
  const [appliedMapping, setAppliedMapping] = useState<ColumnMapping | null>(null)
  const [appliedDraft, setAppliedDraft] = useState<MappingDraft | null>(null)
  const [profileId, setProfileId] = useState<number | undefined>(undefined)
  const [profileName, setProfileName] = useState('')
  const [cardId, setCardId] = useState<number | undefined>(undefined)

  const isChecking = mode === 'checking'
  const { data: profiles = [] } = useQuery({
    queryKey: ['import-profiles'],
    queryFn: () => importProfilesApi.list(),
    enabled: !isChecking,
  })
  const { data: cards = [] } = useQuery({
    queryKey: ['cards'],
    queryFn: () => cardsApi.list(),
    enabled: !isChecking,
  })
  const availableProfiles = profiles.filter((p) => p.source_type === mode)

  const step = result ? 'done' : preview?.mapping_required ? 'mapping' : preview ? 'preview' : 'upload'
  const repeatInfo = useMemo(() => repeatGroupInfo(preview?.rows ?? []), [preview])
  const titles = {
    upload: isChecking ? 'Import checking statement' : 'Import statement',
    mapping: 'Map your columns',
    preview: isChecking ? 'Checking import preview' : 'Import preview',
    done: 'Import complete',
  }
  const uploadCopy = isChecking
    ? 'Drop a checking-account statement. Every row (deposits and withdrawals) becomes a Personal transaction in your inbox.'
    : 'Drop a credit card statement. Supported formats: Account Activity CSV, American Express XLS/XLSX, OFX/QFX bank exports, and most generic CSV exports.'
  const errorsCopy = result && result.skipped_errors > 0 ? ` ${result.skipped_errors} row${result.skipped_errors === 1 ? '' : 's'} could not be parsed and were skipped.` : ''
  const doneCopy = isChecking
    ? `${result?.skipped ?? 0} duplicates skipped.${errorsCopy} New transactions are waiting in the Personal Inbox.`
    : `${result?.skipped ?? 0} duplicates skipped. ${result?.ignored_credits ?? 0} credit transactions ignored.${errorsCopy} New spending is waiting in the Inbox.`

  async function runPreview(nextFile: File, opts: { mapping?: ColumnMapping; profileId?: number; chargesPositive?: boolean; dayFirst?: boolean } = {}) {
    setError('')
    setLoading(true)
    try {
      const next = isChecking
        ? await transactionsApi.previewCheckingImport(nextFile, opts)
        : await transactionsApi.previewImport(nextFile, opts)
      setPreview(next)
      if (!next.mapping_required) {
        setChargesPositive(next.charges_positive)
        setDayFirst(next.day_first)
      }
      return next
    } catch (err) {
      setError((err as Error).message)
      return null
    } finally {
      setLoading(false)
    }
  }

  async function readFile(nextFile: File) {
    setFile(nextFile)
    setAppliedMapping(null)
    setAppliedDraft(null)
    const opts = profileId !== undefined ? { profileId } : {}
    const next = await runPreview(nextFile, opts)
    if (next === null) setFile(null)
    else if (profileId !== undefined) setAppliedMapping(null)
  }

  async function selectProfile(value: string) {
    const id = value ? Number(value) : undefined
    setProfileId(id)
    if (file) {
      setAppliedMapping(null)
      setAppliedDraft(null)
      await runPreview(file, id !== undefined ? { profileId: id } : {})
    }
  }

  async function applyMapping(mapping: ColumnMapping, draft: MappingDraft) {
    if (!file) return
    const next = await runPreview(file, { mapping })
    if (next && !next.mapping_required) {
      setAppliedMapping(mapping)
      setAppliedDraft(draft)
    }
  }

  async function applySign(next: boolean) {
    if (!file) return
    setChargesPositive(next)
    await runPreview(file, {
      chargesPositive: next,
      ...(dayFirst !== undefined ? { dayFirst } : {}),
      ...(appliedMapping ? { mapping: appliedMapping } : {}),
    })
  }

  async function applyDayFirst(next: boolean) {
    if (!file) return
    setDayFirst(next)
    await runPreview(file, {
      dayFirst: next,
      ...(!isChecking && chargesPositive !== undefined ? { chargesPositive } : {}),
      ...(appliedMapping ? { mapping: appliedMapping } : {}),
      ...(profileId !== undefined ? { profileId } : {}),
    })
  }

  const saveProfileMutation = useMutation({
    mutationFn: () => {
      const m = appliedMapping
      const d = appliedDraft
      if (!m) throw new Error('No mapping to save')
      return importProfilesApi.create({
        name: profileName.trim(),
        source_type: mode,
        date_column: m.date_column,
        description_column: m.description_column,
        amount_column: m.amount_column ?? null,
        debit_column: m.debit_column ?? null,
        credit_column: m.credit_column ?? null,
        amount_convention: d?.amount_convention ?? 'signed',
        date_convention: preview?.date_convention_adjustable ? (dayFirst ? 'dmy' : 'mdy') : null,
        ignored_payment_patterns: [],
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['import-profiles'] })
      setProfileName('')
      toast.success('Import profile saved.')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  function invalidateImportQueries() {
    invalidateLedger(qc)
    invalidateAnalytics(qc)
  }

  async function confirm() {
    if (!file) return
    setLoading(true)
    setError('')
    try {
      const confirmOpts = {
        ...(dayFirst !== undefined ? { dayFirst } : {}),
        ...(appliedMapping ? { mapping: appliedMapping } : {}),
        ...(profileId !== undefined ? { profileId } : {}),
      }
      const next = isChecking
        ? await transactionsApi.confirmCheckingImport(file, confirmOpts)
        : await transactionsApi.confirmImport(file, { chargesPositive, ...(cardId !== undefined ? { cardId } : {}), ...confirmOpts })
      setResult(next)
      invalidateImportQueries()
      if (next.imported > 0 && next.batch_id) {
        const batchId = next.batch_id
        const imported = next.imported
        toast.success(`Imported ${imported} transaction${imported === 1 ? '' : 's'}.`, {
          action: {
            label: 'Undo',
            onClick: async () => {
              try {
                await importsApi.deleteBatch(batchId)
                invalidateImportQueries()
                toast.success('Import undone.')
              } catch (err) {
                toast.error((err as Error).message || 'Undo failed')
              }
            },
          },
        })
      }
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
    setChargesPositive(undefined)
    setDayFirst(undefined)
    setAppliedMapping(null)
    setAppliedDraft(null)
    setProfileName('')
    if (fileRef.current) fileRef.current.value = ''
  }

  const footer = step === 'preview' && preview
    ? <><Button variant="secondary" leftIcon={<ArrowLeft className="size-4" />} onClick={reset}>Back</Button><Button onClick={confirm} loading={loading} disabled={preview.to_import === 0}>Import {preview.to_import}</Button></>
    : step === 'mapping'
      ? <Button variant="secondary" leftIcon={<ArrowLeft className="size-4" />} onClick={reset}>Back</Button>
      : step === 'done'
        ? <Button onClick={onClose}>Done</Button>
        : <Button variant="secondary" onClick={onClose}>Cancel</Button>

  return (
    <Modal open onClose={onClose} title={titles[step]} size="xl" footer={footer}>
      {step === 'upload' && (
        <div>
          <p className="mb-5 text-sm leading-relaxed text-[var(--text-muted)]">{uploadCopy}</p>
          {!isChecking && cards.length > 0 && (
            <Field label="Assign to card (optional)" htmlFor="import-card-select" className="mb-4">
              <Select id="import-card-select" value={cardId !== undefined ? String(cardId) : ''} onChange={(e) => setCardId(e.target.value ? Number(e.target.value) : undefined)}>
                <option value="">No card</option>
                {cards.map((c) => <option key={c.id} value={String(c.id)}>{c.name}{c.last4 ? ` ····${c.last4}` : ''}</option>)}
              </Select>
            </Field>
          )}
          {!isChecking && availableProfiles.length > 0 && (
            <Field label="Use a saved import profile" htmlFor="profile-select" className="mb-4">
              <Select id="profile-select" value={profileId !== undefined ? String(profileId) : ''} onChange={(e) => selectProfile(e.target.value)}>
                <option value="">Auto-detect columns</option>
                {availableProfiles.map((p) => <option key={p.id} value={String(p.id)}>{p.name}</option>)}
              </Select>
            </Field>
          )}
          <button type="button" onClick={() => fileRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setDragOver(true) }} onDragLeave={() => setDragOver(false)} onDrop={(e) => { e.preventDefault(); setDragOver(false); const dropped = e.dataTransfer.files[0]; if (dropped) readFile(dropped) }} className={cn('flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-[8px] border-2 border-dashed px-6 py-10 text-sm transition-colors', dragOver ? 'border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]' : 'border-[var(--border-strong)] bg-[var(--surface-muted)] text-[var(--text-subtle)] hover:border-[var(--accent)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]')}>
            {loading ? <><span className="size-6 animate-spin rounded-full border-2 border-current border-r-transparent" /><span>Parsing file...</span></> : <><Upload className="size-7" /><span><strong className="text-[var(--text)]">Choose file</strong> or drag and drop CSV / XLS / XLSX / OFX / QFX</span></>}
          </button>
          <input ref={fileRef} type="file" aria-label="Upload statement file" accept=".csv,.xls,.xlsx,.ofx,.qfx,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/x-ofx,application/vnd.intu.qfx" className="hidden" onChange={(e) => { const picked = e.target.files?.[0]; if (picked) readFile(picked) }} />
          {error && <div role="alert" className="mt-3 rounded-[8px] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)]">{error}</div>}
        </div>
      )}
      {step === 'mapping' && preview && (
        <MappingStep preview={preview} loading={loading} error={error} onApply={applyMapping} />
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
          {!isChecking && preview.amount_sign_adjustable && (
            <label className="mb-4 flex cursor-pointer items-start gap-2.5 rounded-[8px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3 text-sm">
              <input type="checkbox" checked={chargesPositive ?? false} disabled={loading} onChange={(e) => applySign(e.target.checked)} className="mt-0.5 size-4 accent-[var(--accent)]" />
              <span>
                <span className="font-medium text-[var(--text)]">Charges are shown as positive (AmEx-style)</span>
                <span className="mt-0.5 block text-xs text-[var(--text-subtle)]">Turn on if purchases are positive numbers and payments/refunds are negative in your file.</span>
              </span>
            </label>
          )}
          {preview.date_convention_adjustable && (
            <label className="mb-4 flex cursor-pointer items-start gap-2.5 rounded-[8px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3 text-sm">
              <input type="checkbox" checked={dayFirst ?? false} disabled={loading} onChange={(e) => applyDayFirst(e.target.checked)} className="mt-0.5 size-4 accent-[var(--accent)]" />
              <span>
                <span className="font-medium text-[var(--text)]">Dates are day-first (DD/MM)</span>
                <span className="mt-0.5 block text-xs text-[var(--text-subtle)]">Turn on if your file writes May 4 as 04/05. We can&rsquo;t tell automatically when every date could be read either way.</span>
              </span>
            </label>
          )}
          {!isChecking && appliedMapping && (
            <div className="mb-4 flex flex-wrap items-end gap-2 rounded-[8px] border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3">
              <Field label="Save this layout as a profile" htmlFor="save-profile-name" className="flex-1 min-w-[200px]">
                <input id="save-profile-name" value={profileName} onChange={(e) => setProfileName(e.target.value)} placeholder="e.g. My Credit Union" className="w-full rounded-[8px] border border-[var(--border-strong)] bg-[var(--surface-solid)] px-3 py-2 text-sm" />
              </Field>
              <Button variant="secondary" disabled={!profileName.trim() || saveProfileMutation.isPending} onClick={() => saveProfileMutation.mutate()}>Save profile</Button>
            </div>
          )}
          <div className="max-h-[420px] overflow-auto rounded-[8px] border border-[var(--border)]">
            <table className="w-full text-sm"><thead className="sticky top-0 bg-[var(--surface-solid)]"><tr className="border-b border-[var(--border)] text-left text-[11px] uppercase text-[var(--text-subtle)]"><th className="px-3 py-2">Date</th><th className="px-3 py-2">Description</th><th className="px-3 py-2 text-right">Amount</th><th className="px-3 py-2">Status</th></tr></thead><tbody>
              {preview.rows.map((row) => { const repeat = repeatInfo.get(row.row_number); return <tr key={row.row_number} className={cn('border-b border-[var(--border)] last:border-0', (row.is_duplicate || row.is_ignored_credit) && 'opacity-50')}><td className="whitespace-nowrap px-3 py-2 text-xs text-[var(--text-subtle)]">{row.date}</td><td className="max-w-[260px] truncate px-3 py-2 font-medium">{row.description}</td><td className={cn('whitespace-nowrap px-3 py-2 text-right font-bold tabular-nums', row.transaction_type === 'credit' ? 'text-[var(--success)]' : 'text-[var(--danger)]')}>{signedMoney(row.amount_cents, row.transaction_type)}</td><td className="px-3 py-2"><div className="flex flex-wrap items-center gap-1.5">{row.is_ignored_credit ? <Badge tone="warning">credit ignored</Badge> : row.is_duplicate ? <Badge tone="muted">duplicate</Badge> : <Badge tone="success">new</Badge>}{repeat && <Badge tone="muted">repeat in file ({repeat.index} of {repeat.size})</Badge>}</div></td></tr> })}
            </tbody></table>
          </div>
          <SkippedRowsDetails preview={preview} />
          {error && <div role="alert" className="mt-3 rounded-[8px] bg-[var(--danger-soft)] px-3 py-2 text-sm text-[var(--danger)]">{error}</div>}
        </div>
      )}
      {step === 'done' && result && <div className="py-4 text-center"><div className="mx-auto mb-3 flex size-14 items-center justify-center rounded-full bg-[var(--success-soft)] text-[var(--success)]"><CheckCircle2 className="size-8" /></div><p className="text-xl font-bold">{result.imported} transactions imported</p><p className="mt-1 text-sm text-[var(--text-subtle)]">{doneCopy}</p></div>}
    </Modal>
  )
}
