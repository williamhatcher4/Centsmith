# Credit Tracker

A small local app for importing credit card statements, sorting transactions into Personal or Work, reviewing spending, and exporting each group separately.

The app runs entirely on your own computer. Your data never leaves your machine.

---

## Using the desktop app

The desktop app is the simplest way to run Credit Tracker. You just install it like any other Windows program — no Python, Node.js, or command-line setup needed.

### What you'll need

- **Windows 10 or 11** (64-bit)
- **WebView2 Runtime** — already included with Windows 11. On Windows 10, the installer will prompt you to download it automatically if it's missing.

### Installing

1. Download the latest `CreditTracker-Setup-x.x.x.exe` installer.
2. Double-click it and click through the wizard. The defaults are all fine.
3. When it finishes, a **Credit Tracker** shortcut will be on your desktop and in your Start Menu.
4. Double-click the shortcut to launch the app. The first launch takes a few seconds while the local server starts — you'll see a "Starting Credit Tracker…" screen while it loads.

That's it. No login required.

### Where your data lives

The desktop app stores your database at:

```
C:\Users\<your name>\AppData\Roaming\CreditTracker\credit_tracker.db
```

To find it quickly in File Explorer, paste this into the address bar:

```
%APPDATA%\CreditTracker
```

**Back this folder up regularly** — copy it to OneDrive, an external drive, or anywhere you keep important files.

### Moving data from the developer version

If you were previously running Credit Tracker via `start.ps1` and have existing transaction data, you can carry it over:

1. Close both the developer app (the two PowerShell windows) and the desktop app if either is running.
2. Open PowerShell and run:

   ```powershell
   Copy-Item "$env:USERPROFILE\OneDrive\Documents\Projects\credit_tracker\credit_tracker.db" `
             "$env:APPDATA\CreditTracker\credit_tracker.db"
   ```

   Adjust the source path to wherever your `credit_tracker` project folder is.
3. Launch the desktop app — all your transactions will be there.

### Uninstalling

Open **Settings → Apps**, search for Credit Tracker, and click **Uninstall**. Your data in `%APPDATA%\CreditTracker\` is preserved — delete that folder manually if you want to remove it too.

---

## Developer mode (running from source)

Use this if you're working on the code, or if you don't have an installer build available.

### What you'll need

- **Windows 10 or 11**
- **A web browser** (Edge, Chrome, or Firefox — anything modern)
- **Python 3.10 or higher** and **Node.js LTS** — full walkthroughs below

### Installing Python

Python runs the part of the app that handles your data.

1. Open <https://www.python.org/downloads/> in your browser.
2. Click the big yellow **"Download Python 3.x.x"** button.
3. Run the downloaded installer.
4. **Before clicking anything**, tick **"Add python.exe to PATH"** at the bottom of the first screen. This is critical — if you miss it the app won't work.
5. Click **Install Now**. Approve the UAC prompt if it appears, then click **Close** when done.
6. Verify it worked — open a new PowerShell window and run:

   ```powershell
   python --version
   ```

   You should see something like `Python 3.13.1`.

### Installing Node.js

Node.js builds the part of the app you see in the browser.

1. Open <https://nodejs.org> in your browser.
2. Click the **LTS** button (not "Current").
3. Run the downloaded installer, clicking **Next** through every screen with default settings.
4. Verify in a **new** PowerShell window:

   ```powershell
   node --version
   npm --version
   ```

### Getting the code

**Option A — Download a ZIP (no Git needed)**

1. On the GitHub page, click **Code → Download ZIP**.
2. Extract the ZIP to your Documents folder (or anywhere convenient).

**Option B — Git**

```powershell
git clone <repository-url> credit_tracker
```

### First-time setup

You need to set a username and password for the login screen.

1. Run `start.ps1` once (see below). On the very first run it will create `backend\.env` and stop with a yellow message.
2. Open `backend\.env` in Notepad. Fill in your username and password:

   ```
   ADMIN_USERNAME=yourname
   ADMIN_PASSWORD=yourpassword
   ```

   Leave `SECRET_KEY` alone — the script filled it in automatically.
3. Save and close, then run `start.ps1` again.

### Running the app

1. Open the `credit_tracker` folder in File Explorer.
2. Right-click `start.ps1` → **Run with PowerShell**.
3. The first run takes a few minutes to download dependencies and build the frontend. Subsequent runs are quick.
4. When ready, open your browser to <http://localhost:5175> and log in.

To stop the app, close the two PowerShell windows that opened.

### Where your data lives (developer mode)

Your database is `credit_tracker.db` in the project folder. Back it up by copying it somewhere safe.

---

## Building the desktop installer

This section is for creating a new `CreditTracker-Setup-x.x.x.exe` to distribute.

### Prerequisites (one-time)

In addition to Python and Node.js, you'll need:

- **Rust** — install from <https://rustup.rs>. Choose the default options.
- **VS C++ Build Tools** — download "Build Tools for Visual Studio" from [visualstudio.microsoft.com/downloads](https://visualstudio.microsoft.com/downloads/) and select the **"Desktop development with C++"** workload.
- **Tauri CLI** — after installing Rust, run:

  ```powershell
  cargo install tauri-cli --version "^2.0"
  ```

- **Inno Setup 6** — download from <https://jrsoftware.org/isinfo.php>. After installing, add it to your PATH:

  ```powershell
  # Add to your profile so it persists across sessions:
  $env:PATH += ";C:\Program Files (x86)\Inno Setup 6"
  ```

- **App icon** — generate icon files from a 1024×1024 PNG source:

  ```powershell
  cargo tauri icon path\to\source.png --output desktop\src-tauri\icons
  ```

### Building

From the repo root:

```powershell
.\packaging\build.ps1
```

This runs the full pipeline:
1. Builds the React frontend (`npm run build`)
2. Packages the Python backend with PyInstaller
3. Copies the backend bundle into the Tauri shell
4. Compiles the Tauri shell (`cargo tauri build`)
5. Produces `packaging\dist\CreditTracker-Setup-x.x.x.exe` with Inno Setup

The first build takes 10–15 minutes (Cargo compiles all Tauri dependencies from scratch). Subsequent builds are much faster.

**Partial builds** — useful when iterating:

```powershell
# Skip Tauri and Inno Setup (backend changes only):
.\packaging\build.ps1 -SkipTauri

# Release backend bundle path (uses PyArmor):
.\packaging\build.ps1 -SkipTauri -ObfuscateBackend

# Skip Inno Setup (Tauri shell changes only):
.\packaging\build.ps1 -SkipInstaller
```

After staging the backend into `desktop\src-tauri\resources\backend`,
`build.ps1` unconditionally runs `packaging\validate-release-artifacts.ps1`,
which aborts the build if any `.env`, `.pfx`, `.p12`, `.pem`, or `.key` file
— or any file whose name contains `private`, `credential`, `password`,
`signing-key`, or `signing_key` — has slipped into the staged bundle.

### Publishing signed auto-updates

The release workflow publishes signed updater artifacts to the public
`williamhatcher4/credit_tracker_releases` repo while keeping this source repo
private. Before running `.github/workflows/release.yml`, add these secrets to
the private source repo:

- `PUBLIC_RELEASES_TOKEN` - fine-grained token with contents write access to
  `williamhatcher4/credit_tracker_releases`
- `TAURI_SIGNING_PRIVATE_KEY` - contents of `packaging\credit-tracker-updater.key`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` - blank if the generated key has no password
- `WINDOWS_CERTIFICATE_BASE64` - base64 encoded `.pfx` code-signing certificate
- `WINDOWS_CERTIFICATE_PASSWORD` - `.pfx` password

The updater public key is committed in `desktop\src-tauri\tauri.conf.json`.
Keep the private updater key and Windows signing certificate out of git.

---

## Troubleshooting

### Desktop app

**The app opens a loading screen and never gets past it**

The local server is taking longer than expected to start. Wait up to 30 seconds. If it still doesn't load, check whether a previous instance is still running: open Task Manager and look for `credit-tracker-backend.exe`. If you see one, end it, then try launching again.

**"Windows protected your PC" / SmartScreen warning**

The installer isn't code-signed. Click **More info → Run anyway**. This is expected for a privately distributed app without a commercial signing certificate.

**I want to see what the app is doing internally**

Check the shell log:

```powershell
Get-Content "$env:APPDATA\CreditTracker\shell.log"
```

### Developer mode

**"Running scripts is disabled on this system"**

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Run this in PowerShell as Administrator, answer Y, then try `start.ps1` again.

**"Could not find npm"**

Node.js isn't installed or isn't on PATH. Install Node.js LTS from <https://nodejs.org> with default options, then open a new PowerShell window and try again.

**"ADMIN_USERNAME and ADMIN_PASSWORD must be set"**

Open `backend\.env` in Notepad and fill in a username and password. See **First-time setup** above.

**The browser shows "This site can't be reached"**

The servers are still starting. Wait 5–10 seconds and refresh. If the PowerShell windows closed unexpectedly, run `start.ps1` again.

**I forgot my password**

Close the app, delete `credit_tracker.db`, edit `backend\.env` with new credentials, and run `start.ps1` again. This wipes your transaction data — back up the `.db` file first if you want to keep it.

**Port 8012 or 5175 already in use**

`start.ps1` tries to free these ports automatically. If it fails, restarting your computer is the simplest fix.
