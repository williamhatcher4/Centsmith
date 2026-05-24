import { forwardRef, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../utils/cn'

const fieldBase =
  'block w-full rounded-[var(--radius-sm)] border border-[var(--border-solid)] bg-[var(--surface-solid)] ' +
  'px-3 py-2.5 text-sm text-[var(--text)] placeholder:text-[var(--text-faint)] ' +
  'shadow-[var(--shadow-sm)] transition-colors duration-150 ' +
  'focus:border-[var(--accent)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-ring)] ' +
  'disabled:cursor-not-allowed disabled:opacity-60'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(fieldBase, invalid && 'border-[var(--danger)] focus:border-[var(--danger)]', className)}
      {...rest}
    />
  )
})

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, invalid, children, ...rest },
  ref,
) {
  return (
    <div className="relative">
      <select
        ref={ref}
        className={cn(
          fieldBase,
          'appearance-none pr-9 cursor-pointer',
          invalid && 'border-[var(--danger)] focus:border-[var(--danger)]',
          className,
        )}
        {...rest}
      >
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 20 20"
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-[var(--text-subtle)]"
      >
        <path
          fill="currentColor"
          fillRule="evenodd"
          d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.06l3.71-3.83a.75.75 0 1 1 1.08 1.04l-4.25 4.39a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z"
          clipRule="evenodd"
        />
      </svg>
    </div>
  )
})

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      className={cn(
        fieldBase,
        'min-h-[80px] resize-y',
        invalid && 'border-[var(--danger)] focus:border-[var(--danger)]',
        className,
      )}
      {...rest}
    />
  )
})

export function Label({
  children,
  htmlFor,
  className,
  hint,
}: {
  children: ReactNode
  htmlFor?: string
  className?: string
  hint?: ReactNode
}) {
  return (
    <div className={cn('mb-1.5 flex items-baseline justify-between gap-2', className)}>
      <label htmlFor={htmlFor} className="text-xs font-semibold text-[var(--text-muted)]">
        {children}
      </label>
      {hint && <span className="text-xs text-[var(--text-faint)]">{hint}</span>}
    </div>
  )
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
  className,
}: {
  label?: ReactNode
  htmlFor?: string
  hint?: ReactNode
  error?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('mb-4', className)}>
      {label && (
        <Label htmlFor={htmlFor} hint={hint}>
          {label}
        </Label>
      )}
      {children}
      {error && <p className="mt-1.5 text-xs text-[var(--danger)]">{error}</p>}
    </div>
  )
}
