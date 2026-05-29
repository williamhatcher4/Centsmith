import { cn } from '../../utils/cn'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[var(--radius-sm)] bg-[var(--surface-muted)]',
        // moving sheen sweep
        'after:absolute after:inset-0 after:-translate-x-full',
        'after:bg-[linear-gradient(90deg,transparent,var(--surface-strong),transparent)]',
        'after:animate-[shimmer_1.6s_ease-in-out_infinite]',
        className,
      )}
    />
  )
}
