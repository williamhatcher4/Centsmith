import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useCountUp } from './useCountUp'

describe('useCountUp', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('returns the target immediately when animation is unavailable (jsdom)', () => {
    const { result } = renderHook(() => useCountUp(500))
    expect(result.current).toBe(500)
  })

  it('returns the target immediately when disabled', () => {
    const { result } = renderHook(() => useCountUp(123, { enabled: false }))
    expect(result.current).toBe(123)
  })

  it('settles on a new target when it changes', () => {
    const { result, rerender } = renderHook(({ t }) => useCountUp(t), {
      initialProps: { t: 10 },
    })
    expect(result.current).toBe(10)
    rerender({ t: 42 })
    expect(result.current).toBe(42)
  })

  it('does not animate when the user prefers reduced motion', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener() {},
      removeEventListener() {},
    }))
    vi.stubGlobal('requestAnimationFrame', () => 1)
    const { result } = renderHook(() => useCountUp(999))
    expect(result.current).toBe(999)
  })

  it('animates from 0 and settles exactly on the target when motion is allowed', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: false,
      addEventListener() {},
      removeEventListener() {},
    }))
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      frames.push(cb)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', () => {})
    const nowSpy = vi.spyOn(performance, 'now').mockReturnValue(0)

    const { result } = renderHook(() => useCountUp(100, { duration: 200 }))
    expect(result.current).toBe(0)

    // Advance past the duration and run the queued frame.
    nowSpy.mockReturnValue(1000)
    act(() => {
      frames[frames.length - 1](1000)
    })
    expect(result.current).toBe(100)
  })
})
