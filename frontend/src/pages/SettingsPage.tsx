import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Pencil, Plus, Trash2, X } from 'lucide-react'
import { settingsApi, type UpdateSettingsOptions } from '../api/settings'
import type { UserSettings } from '../types'
import { ACCENTS, Button, Card, CardHeader, Field, IconButton, Input, PageHeader, SegmentedControl, Select, Skeleton, useTheme, type Theme } from '../components/ui'
import { useToast } from '../components/ui/Toaster'
import { cn } from '../utils/cn'
import { SYSTEM_CATEGORIES } from '../hooks/useCategories'
import { HIDEABLE_NAV_LINKS } from '../constants/nav'

const SYSTEM_SET = new Set<string>(SYSTEM_CATEGORIES)

interface CategoryRowProps {
  name: string
  usageCount: number
  isSystem: boolean
  busy: boolean
  onRename: (newName: string) => void
  onDelete: () => void
}

function CategoryRow({ name, usageCount, isSystem, busy, onRename, onDelete }: CategoryRowProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(name)
  const [error, setError] = useState('')

  function startEdit() {
    setDraft(name)
    setError('')
    setEditing(true)
  }

  function cancelEdit() {
    setEditing(false)
    setDraft(name)
    setError('')
  }

  function submitEdit() {
    const next = draft.trim()
    if (!next) {
      setError('Name cannot be empty')
      return
    }
    if (next.length > 80) {
      setError('Name must be ≤80 characters')
      return
    }
    if (next === name) {
      setEditing(false)
      return
    }
    onRename(next)
    setEditing(false)
  }

  return (
    <div className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3 last:border-0">
      {editing ? (
        <>
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            invalid={!!error}
            aria-label={`Rename ${name}`}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitEdit()
              if (e.key === 'Escape') cancelEdit()
            }}
            className="max-w-xs"
          />
          {error && <span className="text-xs text-[var(--danger)]">{error}</span>}
          <div className="ml-auto flex items-center gap-1">
            <IconButton aria-label={`Save ${name}`} icon={<Check className="size-4" />} onClick={submitEdit} size="sm" />
            <IconButton aria-label={`Cancel rename ${name}`} icon={<X className="size-4" />} onClick={cancelEdit} size="sm" />
          </div>
        </>
      ) : (
        <>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span className="truncate text-sm font-medium text-[var(--text)]">{name}</span>
            {isSystem && (
              <span
                title="System category — required and cannot be renamed or removed"
                className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-semibold uppercase text-[var(--text-subtle)]"
              >
                System
              </span>
            )}
            {usageCount > 0 && (
              <span className="text-xs text-[var(--text-subtle)]">
                {usageCount} {usageCount === 1 ? 'transaction' : 'transactions'}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <IconButton
              aria-label={`Rename ${name}`}
              icon={<Pencil className="size-4" />}
              onClick={startEdit}
              size="sm"
              disabled={isSystem || busy}
            />
            <IconButton
              aria-label={`Delete ${name}`}
              icon={<Trash2 className="size-4" />}
              onClick={onDelete}
              variant="danger"
              size="sm"
              disabled={isSystem || busy}
            />
          </div>
        </>
      )}
    </div>
  )
}

interface DeleteDialogState {
  name: string
  usageCount: number
}

function DeleteCategoryModal({
  state,
  remainingCategories,
  onCancel,
  onConfirm,
}: {
  state: DeleteDialogState
  remainingCategories: string[]
  onCancel: () => void
  onConfirm: (relabelTo: string | null) => void
}) {
  const defaultTarget = remainingCategories.find((c) => c === 'Other') ?? remainingCategories[0] ?? ''
  const [target, setTarget] = useState(defaultTarget)
  const inUse = state.usageCount > 0

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/45 backdrop-blur-md animate-[fadeIn_200ms_var(--ease-out)]" onClick={onCancel} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Delete ${state.name}`}
        className="relative w-full max-w-md rounded-[var(--radius-xl)] border border-[var(--border-strong)] bg-[var(--surface-strong)] p-5 shadow-[var(--shadow-lg)] ring-1 ring-inset ring-white/10 backdrop-blur-2xl animate-[slideUp_280ms_var(--ease-drawer)]"
      >
        <h2 className="text-lg font-semibold text-[var(--text)]">Delete &ldquo;{state.name}&rdquo;?</h2>
        {inUse ? (
          <>
            <p className="mt-2 text-sm text-[var(--text-subtle)]">
              {state.usageCount} {state.usageCount === 1 ? 'transaction uses' : 'transactions use'} this category. Pick a category to move those rows to.
            </p>
            <Field label="Relabel to" htmlFor="relabel-target" className="mt-4">
              <Select id="relabel-target" value={target} onChange={(e) => setTarget(e.target.value)}>
                {remainingCategories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </Select>
            </Field>
          </>
        ) : (
          <p className="mt-2 text-sm text-[var(--text-subtle)]">
            No transactions use this category. It will simply be removed from your list.
          </p>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
          <Button
            variant="danger"
            onClick={() => onConfirm(inUse ? target : null)}
            disabled={inUse && !target}
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  )
}

export function SettingsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { theme, setTheme, accent, setAccent } = useTheme()
  const [newCategory, setNewCategory] = useState('')
  const [addError, setAddError] = useState('')
  const [deleteState, setDeleteState] = useState<DeleteDialogState | null>(null)
  const [hiddenDraft, setHiddenDraft] = useState<string[] | null>(null)

  const { data: settings, isLoading: settingsLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: () => settingsApi.get(),
  })
  const { data: usage = {}, isLoading: usageLoading } = useQuery({
    queryKey: ['settings', 'category-usage'],
    queryFn: () => settingsApi.getCategoryUsage(),
  })

  const categories = useMemo(() => settings?.personal_categories ?? [], [settings?.personal_categories])

  const updateMutation = useMutation({
    mutationFn: ({ payload, opts }: { payload: UserSettings; opts?: UpdateSettingsOptions }) =>
      settingsApi.update(payload, opts),
    onSuccess: (next) => {
      qc.setQueryData(['settings'], next)
      qc.invalidateQueries({ queryKey: ['settings', 'category-usage'] })
      qc.invalidateQueries({ queryKey: ['transactions'] })
      qc.invalidateQueries({ queryKey: ['spending'] })
      qc.invalidateQueries({ queryKey: ['income'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })

  const lowerSet = useMemo(() => new Set(categories.map((c) => c.toLowerCase())), [categories])

  function addCategory() {
    const next = newCategory.trim()
    setAddError('')
    if (!next) {
      setAddError('Name cannot be empty')
      return
    }
    if (next.length > 80) {
      setAddError('Name must be ≤80 characters')
      return
    }
    if (lowerSet.has(next.toLowerCase())) {
      setAddError('That category already exists')
      return
    }
    const payload: UserSettings = {
      personal_categories: [...categories, next],
      hidden_pages: settings?.hidden_pages ?? [],
    }
    updateMutation.mutate(
      { payload },
      {
        onSuccess: () => {
          setNewCategory('')
          toast.success(`Added "${next}"`)
        },
        onError: (err: Error) => setAddError(err.message),
      },
    )
  }

  function renameCategory(oldName: string, newName: string) {
    if (lowerSet.has(newName.toLowerCase()) && newName.toLowerCase() !== oldName.toLowerCase()) {
      toast.error('That category already exists')
      return
    }
    const renamed = categories.map((c) => (c === oldName ? newName : c))
    const payload: UserSettings = {
      personal_categories: renamed,
      hidden_pages: settings?.hidden_pages ?? [],
    }
    updateMutation.mutate(
      { payload, opts: { on_delete: 'relabel', relabel_target: newName } },
      {
        onSuccess: () => toast.success(`Renamed to "${newName}"`),
        onError: (err: Error) => toast.error(err.message),
      },
    )
  }

  function openDelete(name: string) {
    setDeleteState({ name, usageCount: usage[name] ?? 0 })
  }

  function confirmDelete(relabelTo: string | null) {
    if (!deleteState) return
    const name = deleteState.name
    const remaining = categories.filter((c) => c !== name)
    const payload: UserSettings = {
      personal_categories: remaining,
      hidden_pages: settings?.hidden_pages ?? [],
    }
    const opts: UpdateSettingsOptions | undefined = relabelTo
      ? { on_delete: 'relabel', relabel_target: relabelTo }
      : undefined
    setDeleteState(null)
    updateMutation.mutate(
      { payload, opts },
      {
        onSuccess: () => toast.success(`Deleted "${name}"`),
        onError: (err: Error) => toast.error(err.message),
      },
    )
  }

  const hiddenPages = settings?.hidden_pages ?? []
  const draft = hiddenDraft ?? hiddenPages
  const draftSet = new Set(draft)
  const visibleCount = HIDEABLE_NAV_LINKS.length - draft.filter((p) => HIDEABLE_NAV_LINKS.some((l) => l.to === p)).length
  const pagesDirty = hiddenDraft !== null && (
    draft.length !== hiddenPages.length || draft.some((p) => !hiddenPages.includes(p))
  )
  const pagesInvalid = visibleCount < 1
  const pagesSaveDisabled = !pagesDirty || pagesInvalid || updateMutation.isPending

  function togglePage(slug: string) {
    const current = hiddenDraft ?? hiddenPages
    const next = current.includes(slug) ? current.filter((p) => p !== slug) : [...current, slug]
    setHiddenDraft(next)
  }

  function savePages() {
    if (pagesSaveDisabled) return
    const payload: UserSettings = {
      personal_categories: categories,
      hidden_pages: draft,
    }
    updateMutation.mutate(
      { payload },
      {
        onSuccess: () => {
          setHiddenDraft(null)
          toast.success('Page visibility updated')
        },
        onError: (err: Error) => toast.error(err.message),
      },
    )
  }

  function resetPages() {
    setHiddenDraft(null)
  }

  if (settingsLoading) return <Skeleton className="h-64" />

  const remainingForRelabel = categories.filter((c) => c !== deleteState?.name)

  return (
    <div>
      <PageHeader eyebrow="Preferences" title="Settings" subtitle="Customize categories and other preferences" />
      <Card padding="md" className="mb-6">
        <CardHeader title="Appearance" subtitle="Theme and accent color for the whole app." />
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm font-medium text-[var(--text)]">Theme</div>
              <div className="text-xs text-[var(--text-subtle)]">Light or dark surfaces</div>
            </div>
            <SegmentedControl
              aria-label="Theme"
              value={theme}
              onChange={(v) => setTheme(v as Theme)}
              options={[{ label: 'Light', value: 'light' }, { label: 'Dark', value: 'dark' }]}
            />
          </div>
          <div>
            <div className="text-sm font-medium text-[var(--text)]">Accent color</div>
            <div className="mb-3 text-xs text-[var(--text-subtle)]">Tints buttons, highlights, active nav, and the brand mark</div>
            <div className="flex flex-wrap gap-2.5">
              {ACCENTS.map((a) => {
                const selected = accent === a.id
                return (
                  <button
                    key={a.id}
                    type="button"
                    aria-label={`${a.label} accent`}
                    aria-pressed={selected}
                    onClick={() => setAccent(a.id)}
                    className={cn(
                      'relative size-9 rounded-full ring-2 ring-offset-2 ring-offset-[var(--surface-solid)] transition-transform active:scale-95',
                      selected ? 'ring-[var(--text)]' : 'ring-transparent hover:scale-110',
                    )}
                    style={{ background: a.swatch }}
                  >
                    {selected && <Check className="absolute inset-0 m-auto size-4 text-white drop-shadow" />}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </Card>
      <Card padding="md" className="mb-6">
        <CardHeader
          title="Personal categories"
          subtitle="Categories shown when sorting personal transactions. Income, Reimbursement, and Transfer are required."
        />
        <div className="mb-4 flex gap-2">
          <Input
            value={newCategory}
            onChange={(e) => { setNewCategory(e.target.value); setAddError('') }}
            placeholder="New category name"
            invalid={!!addError}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addCategory() } }}
            aria-label="New category name"
          />
          <Button
            leftIcon={<Plus className="size-4" />}
            onClick={addCategory}
            disabled={updateMutation.isPending}
          >
            Add
          </Button>
        </div>
        {addError && <p className="-mt-2 mb-3 text-sm text-[var(--danger)]">{addError}</p>}
        <div className="rounded-[var(--radius-md)] border border-[var(--border)]">
          {categories.length === 0 ? (
            <p className="px-4 py-6 text-sm text-[var(--text-subtle)]">No categories yet.</p>
          ) : (
            categories.map((name) => (
              <CategoryRow
                key={name}
                name={name}
                usageCount={usage[name] ?? 0}
                isSystem={SYSTEM_SET.has(name)}
                busy={updateMutation.isPending || usageLoading}
                onRename={(newName) => renameCategory(name, newName)}
                onDelete={() => openDelete(name)}
              />
            ))
          )}
        </div>
      </Card>
      <Card padding="md" className="mb-6">
        <CardHeader
          title="Pages"
          subtitle="Choose which pages appear in the navigation. Settings is always visible."
        />
        <div className="rounded-[var(--radius-md)] border border-[var(--border)]">
          {HIDEABLE_NAV_LINKS.map(({ to, label, icon: Icon }) => {
            const checked = !draftSet.has(to)
            const lastVisible = checked && visibleCount === 1
            return (
              <label
                key={to}
                className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-3 last:border-0"
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => togglePage(to)}
                  disabled={lastVisible || updateMutation.isPending}
                  aria-label={`Show ${label}`}
                  className="size-4 accent-[var(--accent)]"
                />
                <Icon className="size-[18px] text-[var(--text-subtle)]" aria-hidden />
                <span className="text-sm font-medium text-[var(--text)]">{label}</span>
                {lastVisible && (
                  <span className="ml-auto text-xs text-[var(--text-subtle)]">
                    At least one page must stay visible
                  </span>
                )}
              </label>
            )
          })}
        </div>
        {pagesInvalid && (
          <p role="alert" className="mt-3 text-sm text-[var(--danger)]">
            At least one page must remain visible.
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          {pagesDirty && (
            <Button variant="ghost" onClick={resetPages} disabled={updateMutation.isPending}>
              Cancel
            </Button>
          )}
          <Button onClick={savePages} disabled={pagesSaveDisabled}>
            Save pages
          </Button>
        </div>
      </Card>
      {deleteState && (
        <DeleteCategoryModal
          state={deleteState}
          remainingCategories={remainingForRelabel}
          onCancel={() => setDeleteState(null)}
          onConfirm={confirmDelete}
        />
      )}
    </div>
  )
}
