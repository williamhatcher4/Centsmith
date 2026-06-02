import { cn } from '../../utils/cn'
import { useReducedMotion } from '../../hooks/useReducedMotion'

interface Blob {
  position: string
  glow: string
  animation: string
}

const BLOBS: Blob[] = [
  {
    position: '-top-[20%] -left-[10%] size-[60vmax]',
    glow: 'var(--glow-1)',
    animation: 'auroraDrift 24s var(--ease-in-out) infinite',
  },
  {
    position: '-top-[12%] -right-[14%] size-[46vmax]',
    glow: 'var(--glow-2)',
    animation: 'auroraDrift 30s var(--ease-in-out) infinite reverse',
  },
  {
    position: '-bottom-[26%] left-[18%] size-[56vmax]',
    glow: 'var(--glow-3)',
    animation: 'auroraDrift 28s var(--ease-in-out) -8s infinite',
  },
]

/**
 * Fixed, purely decorative ambient layer of slowly drifting gradient blobs.
 * Sits behind app content (`-z-10`) and shows through the frosted glass
 * surfaces above it. Drift is disabled under reduced motion.
 */
export function AuroraBackground({ className }: { className?: string }) {
  const reduced = useReducedMotion()
  return (
    <div
      aria-hidden="true"
      className={cn('pointer-events-none fixed inset-0 -z-10 overflow-hidden', className)}
    >
      {BLOBS.map((blob, i) => (
        <div
          key={i}
          className={cn('absolute rounded-full blur-[64px]', blob.position)}
          style={{
            background: `radial-gradient(circle at center, ${blob.glow}, transparent 70%)`,
            animation: reduced ? undefined : blob.animation,
          }}
        />
      ))}
    </div>
  )
}
