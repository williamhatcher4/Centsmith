# Centsmith — Desktop Shell

Native Windows app shell built with Tauri 2. Wraps the FastAPI backend (packaged
as a PyInstaller sidecar) in a WebView2 window so users get a real desktop app
icon and Start Menu entry instead of a browser tab.

## Prerequisites (dev machine only)

End users do **not** need these — they just run the installer.

1. **Rust** — install via [rustup.rs](https://rustup.rs).
2. **Tauri CLI** — `cargo install tauri-cli --version "^2.0"`.
3. **WebView2 Runtime** — pre-installed on Windows 11; Tauri's installer
   bootstraps it on Windows 10 automatically.
4. **Microsoft C++ Build Tools** — required by Rust on Windows. Installed via
   Visual Studio Build Tools (the "Desktop development with C++" workload).

## Layout

```
desktop/
  loader/index.html        # tiny splash shown while sidecar boots
  src-tauri/
    Cargo.toml             # Rust crate manifest
    tauri.conf.json        # Tauri config (window, bundling, resources)
    build.rs               # Tauri build hook
    src/
      main.rs              # entry point
      lib.rs               # window setup + sidecar lifecycle
    capabilities/
      default.json         # window permissions
    icons/                 # app icons (PNG/ICO) — see Icons section
    resources/backend/     # populated by packaging/build.ps1, NOT checked in
```

The Tauri shell never bundles the React app directly — the PyInstaller sidecar
serves both the API and the static `frontend/dist` on `http://127.0.0.1:<port>`.
On launch, Tauri shows `loader/index.html`, then once the sidecar writes
`%APPDATA%\Centsmith\runtime.json`, Tauri reads the local port plus a
one-time desktop login token and navigates the WebView to the authenticated
local URL.

## Building

From the repo root:

```powershell
./packaging/build.ps1
```

That script does the full pipeline: builds the frontend, packages the backend
with PyInstaller, copies it into `desktop/src-tauri/resources/backend/`, then
runs `cargo tauri build`.

For a fast inner dev loop on the shell itself:

```powershell
# (after running build.ps1 once to produce the sidecar bundle)
cd desktop/src-tauri
cargo tauri dev
```

## Icons

Tauri expects icons in `desktop/src-tauri/icons/`. Generate them once from a
single 1024×1024 PNG using:

```powershell
cargo tauri icon path/to/source.png
```

Until you do, `cargo tauri build` will fail at the bundle step. The Rust build
itself runs fine without icons.
