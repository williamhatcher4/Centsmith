import { cn } from '../../utils/cn'

function initialsOf(name?: string) {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function Avatar({ name, size = 'md', className }: { name?: string; size?: 'sm' | 'md'; className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'inline-flex items-center justify-center rounded-full font-semibold',
        'bg-gradient-to-br from-[var(--accent)] to-[var(--chart-5,_#EC4899)] text-white',
        size === 'sm' ? 'size-7 text-[11px]' : 'size-9 text-xs',
        className,
      )}
    >
      {initialsOf(name)}
    </div>
  )
}
