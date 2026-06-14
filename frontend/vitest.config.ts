import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/test/**',
        'src/main.tsx',
        'src/App.tsx',
        'src/types.ts',
        'src/components/ui/**',
      ],
      // Gates ratcheted to actual-5 (P5.2, 2026-06-12). Measured actuals:
      // statements 80.11 / branches 73 / functions 75.91 / lines 83.07.
      // Re-ratchet to actual-5 after any item that adds a meaningful test batch;
      // never lower a gate to merge — shrink the change or add tests instead.
      thresholds: {
        lines: 78,
        functions: 70,
        statements: 75,
        branches: 68,
      },
    },
  },
})
