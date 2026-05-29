import { useEffect, useRef, useState } from 'react'
import { useReducedMotion } from './useReducedMotion'

interface Options {
  /** Animation length in ms. */
  duration?: number
  /** Opt out without changing call sites. */
  enabled?: boolean
}

function canAnimate(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    typeof window.requestAnimationFrame === 'function' &&
    typeof performance !== 'undefined'
  )
}

// Cubic ease-out — mirrors the feel of the --ease-out token.
function easeOut(t: number): number {
  return 1 - Math.pow(1 - t, 3)
}

/**
 * Animates a number toward `target`.
 *
 * Returns the exact `target` (with no state involved) whenever animation is
 * unavailable — reduced motion, SSR, or jsdom/tests with no `matchMedia` /
 * `requestAnimationFrame`. This keeps text assertions like
 * `findByText('$500.00')` stable while still animating in real browsers.
 *
 * Retargeting mid-flight is interruptible: a new `target` eases from the value
 * currently on screen rather than restarting from zero.
 */
export function useCountUp(target: number, { duration = 700, enabled = true }: Options = {}): number {
  const reduced = useReducedMotion()
  const animate = enabled && !reduced && canAnimate() && Number.isFinite(target)
  const [animatedValue, setAnimatedValue] = useState(0)
  // Tracks the most recent animated value; only ever written inside rAF.
  const fromRef = useRef(0)

  useEffect(() => {
    if (!animate) return
    const from = fromRef.current
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const value = from + (target - from) * easeOut(t)
      fromRef.current = value
      setAnimatedValue(value)
      if (t < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
        setAnimatedValue(target)
      }
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, animate])

  return animate ? animatedValue : target
}
