// `npm run audit`: npm audit at moderate+ severity, with a short, explicit
// allowlist for advisories that have no published fix yet. Every entry needs
// a reason and should be removed as soon as a patched version exists.
// See PROJECT_OVERVIEW.md -> "CI Toolchain Pins And Dependency Audits".
import { execFileSync } from 'node:child_process'

const ALLOWED = {
  // picomatch ReDoS (high). Affects every published picomatch (<=4.0.7) and
  // reaches us only through dev/build tooling (vite, vitest, tinyglobby,
  // typescript-eslint); it is not shipped in the app bundle.
  'GHSA-fc5q-39xc-vjpf': 'no patched picomatch release yet; dev/build tooling only',
}

const FAIL_LEVELS = new Set(['moderate', 'high', 'critical'])

let raw
try {
  raw = execFileSync('npm', ['audit', '--json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] })
} catch (err) {
  // npm audit exits non-zero when it finds anything; the JSON is still on stdout.
  raw = err.stdout
  if (!raw) throw err
}

const report = JSON.parse(raw)
const advisories = new Map()
for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vuln.via ?? []) {
    if (typeof via !== 'object' || !FAIL_LEVELS.has(via.severity)) continue
    const id = String(via.url ?? '').split('/').pop() || String(via.source)
    advisories.set(id, { ...via, id, pkg: via.name ?? vuln.name })
  }
}

const blocking = [...advisories.values()].filter((a) => !(a.id in ALLOWED))
const allowed = [...advisories.values()].filter((a) => a.id in ALLOWED)

for (const a of allowed) {
  console.log(`allowed: ${a.id} ${a.pkg} (${a.severity}) - ${ALLOWED[a.id]}`)
}
for (const id of Object.keys(ALLOWED)) {
  if (!advisories.has(id)) console.log(`note: allowlisted ${id} no longer reported; remove it from scripts/audit.mjs`)
}

if (blocking.length) {
  console.error(`\n${blocking.length} moderate+ advisories not on the allowlist:`)
  for (const a of blocking) console.error(`  ${a.id} ${a.pkg} (${a.severity}) ${a.title} ${a.url ?? ''}`)
  process.exit(1)
}
console.log('npm audit: no blocking advisories.')
