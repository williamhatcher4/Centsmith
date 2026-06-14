# Changelog

All notable changes to Centsmith are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com); versions follow the released tag (vx.y.z).

The body under each `## [x.y.z]` heading is published as that release's notes — shown in the desktop
auto-update dialog and on the website download feed. When cutting a release, rename `[Unreleased]` to
`## [x.y.z] - YYYY-MM-DD` and add a fresh empty `[Unreleased]` section above it. A release with no
matching section fails the release workflow on purpose, so every release ships with notes.

## [0.2.7] - 2026-06-13
### Added
- Edit the amount and debit/credit type of manually added transactions (imported
  rows stay locked to match your bank statement).
- Choose a custom backup folder in Settings → Data & diagnostics — point backups
  at another drive so they survive a disk failure. Automatic pre-update backups
  follow it too.
- The Transactions page now shows both money in and money out, with a new Type
  filter to narrow to just credits or just debits.
- Imports understand day-first dates: flip a toggle in the import preview if your
  bank writes May 4 as 04/05.
- CSV exports now include income and refunds alongside spending, with a signed
  Amount, a Type column, and a Category column on personal exports.
- Categories you assign while sorting transactions are remembered automatically,
  so they show up in your filters and category lists without a trip to Settings.
### Changed
- If Centsmith fails to start, the launch window now explains what went wrong and
  how to recover instead of spinning forever.
### Fixed
- Dashboard totals — spending, income, and "Awaiting reimbursement" — now refresh
  right away after you toggle a transaction's expensed status or undo a delete,
  instead of showing stale numbers.
- The backup confirmation's "Open folder" button now opens your actual backup
  folder, and an unavailable backup folder reports a clear error instead of
  failing silently.

## [0.2.6] - 2026-06-05
### Added
- Statements page, automatic billing, and data backups.
- Spending category drill-down to filtered Transactions.
- See your spending categories in detail
### Fixed
- Auto-update functionality.
- Export time.
