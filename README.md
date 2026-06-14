# Centsmith

A small local app for importing credit card statements, sorting transactions into Personal or Work, reviewing spending, and exporting each group separately.

The app runs entirely on your own computer. Your data never leaves your machine.

---

## What you'll need

- **Windows 10 or 11** (64-bit)
- **WebView2 Runtime** — already included with Windows 11. On Windows 10, the installer will prompt you to download it automatically if it's missing.

## Installing

1. Download the latest `Centsmith-Setup-x.x.x.exe` installer.
2. Double-click it and click through the wizard. The defaults are all fine.
3. When it finishes, a **Centsmith** shortcut will be on your desktop and in your Start Menu.
4. Double-click the shortcut to launch the app. The first launch takes a few seconds while the local server starts — you'll see a "Starting Centsmith…" screen while it loads.

That's it. No login required.

> **"Windows protected your PC" / SmartScreen warning?** The installer isn't code-signed. Click **More info → Run anyway**. This is expected for a privately distributed app.

## Where your data lives

The app stores your database at:

```
C:\Users\<your name>\AppData\Roaming\Centsmith\centsmith.db
```

To find it quickly in File Explorer, paste this into the address bar:

```
%APPDATA%\Centsmith
```

**Back this folder up regularly** — copy it to OneDrive, an external drive, or anywhere you keep important files.

## Uninstalling

Open **Settings → Apps**, search for Centsmith, and click **Uninstall**. Your data in `%APPDATA%\Centsmith\` is preserved — delete that folder manually if you want to remove it too.

---

## Troubleshooting

**The app opens a loading screen and never gets past it**

The local server is taking longer than expected to start. Wait up to 30 seconds. If it still doesn't load, check whether a previous instance is still running: open Task Manager and look for `centsmith-backend.exe`. If you see one, end it, then try launching again.

**I want to see what the app is doing internally**

Check the shell log:

```powershell
Get-Content "$env:APPDATA\Centsmith\shell.log"
```
