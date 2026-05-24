# Credit Tracker

A small local app for importing credit card statements, sorting transactions into Personal or Work, reviewing spending, and exporting each group separately.

The app runs entirely on your own computer. Your data never leaves your machine.

## What you'll need

- **Windows 10 or 11**
- **A web browser** (Edge, Chrome, or Firefox — anything modern)
- **Python** and **Node.js** — full walkthroughs below

### Installing Python

Python runs the part of the app that handles your data.

1. Open <https://www.python.org/downloads/> in your browser.
2. You'll see a big yellow button near the top that says **"Download Python 3.x.x"** (the exact version number doesn't matter as long as it's 3.10 or higher). Click it.
3. The installer file (something like `python-3.13.1-amd64.exe`) downloads to your `Downloads` folder. Double-click it to run it.
4. **Important — read this before clicking anything in the installer.** The first screen has two checkboxes near the bottom:
   - ☐ Use admin privileges when installing py.exe
   - ☐ **Add python.exe to PATH** ← **TICK THIS ONE**

   The "Add python.exe to PATH" checkbox is critical. If you miss it, the app won't be able to find Python and you'll have to uninstall and reinstall. **Tick it before clicking anything else.**
5. Click **Install Now** (the top option). Approve the Windows User Account Control prompt if it appears.
6. Wait for the installer to finish (usually under a minute), then click **Close**.
7. **Verify it worked.** Press the Windows key, type `PowerShell`, and open it. In the window that opens, type:

   ```powershell
   python --version
   ```

   Press Enter. You should see something like `Python 3.13.1`. If you see that, Python is installed correctly.

   If instead you see `'python' is not recognized as an internal or external command`, the "Add to PATH" box wasn't ticked. Uninstall Python from **Settings → Apps**, then run the installer again and tick the box this time.

### Installing Node.js

Node.js runs the part of the app you see in your browser.

1. Open <https://nodejs.org> in your browser.
2. The page shows two big download buttons. Click the one labeled **LTS** (it says something like "Recommended For Most Users"). **Do not click the "Current" button** — that's a newer, less stable version.
3. The installer (`node-v22.x.x-x64.msi` or similar) downloads to your `Downloads` folder. Double-click it.
4. Click **Next** through the installer. The default settings are correct — don't change anything. The screens are:
   - Welcome → **Next**
   - License Agreement → tick "I accept" → **Next**
   - Destination Folder → **Next** (leave as `C:\Program Files\nodejs\`)
   - Custom Setup → **Next** (don't deselect anything)
   - "Tools for Native Modules" → **Next** (leave the box unticked; you don't need this for Credit Tracker)
   - Ready to Install → **Install**
5. Approve the Windows User Account Control prompt. Wait for the installer to finish, then click **Finish**.
6. **Verify it worked.** Close any existing PowerShell windows, then open a **new** PowerShell window (Windows key → type `PowerShell` → Enter). In the new window, type:

   ```powershell
   node --version
   npm --version
   ```

   Press Enter after each line. You should see version numbers like `v22.11.0` and `10.9.0`. If you see those, Node.js is installed correctly.

   You must use a **new** PowerShell window after installing — windows opened before the install won't see the new programs.

## Getting the code

Pick whichever option feels easier.

### Option A — Download a ZIP (easiest, no Git needed)

1. Open the GitHub page for this project in your browser.
2. Click the green **Code** button, then **Download ZIP**.
3. Find the downloaded ZIP in your `Downloads` folder.
4. Right-click it → **Extract All...** and choose a folder (for example, your `Documents` folder).
5. Open the extracted folder. The rest of this guide assumes it's called `credit_tracker`.

### Option B — Use Git

1. Install Git from <https://git-scm.com> if you don't already have it.
2. Open PowerShell and run:

   ```powershell
   git clone <repository-url> credit_tracker
   ```

## First-time setup (one time only)

You need to set a username and password for logging into the app. There are two ways to do this — pick whichever you prefer.

### Easy way: let the start script create the file for you

1. Skip ahead to **Running the app** below and run `start.ps1` once.
2. On the very first run, it will create a file called `.env` inside the `backend` folder and then stop with a yellow message telling you to fill in your credentials.
3. Open `backend\.env` in Notepad. You'll see:

   ```
   ADMIN_USERNAME=
   ADMIN_PASSWORD=
   SECRET_KEY=<a long random string>
   ```

4. Type your chosen username after `ADMIN_USERNAME=` and your chosen password after `ADMIN_PASSWORD=`. Leave the `SECRET_KEY` line alone — the script filled it in for you.
5. Save and close the file.
6. Run `start.ps1` again. This time it will keep going.

### Manual way: set it up before the first run

1. Open the `credit_tracker\backend` folder.
2. Find the file called `.env.example`. Make a copy in the same folder and rename the copy to exactly `.env`.
   - In File Explorer, turn on **View → File name extensions** if you can't tell whether the file ends in `.txt`. The file must be just `.env` with no other extension.
3. Open `.env` in Notepad and fill in `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Leave `SECRET_KEY=__AUTO__` — the start script will replace it with a random value automatically.
4. Save and close.

## Running the app

1. Open the `credit_tracker` folder in File Explorer.
2. Right-click `start.ps1` → **Run with PowerShell**.
   - If Windows blocks the script, see **Troubleshooting** below.
3. **The first run takes a few minutes** — it downloads Python and JavaScript libraries and builds the frontend. You'll see progress messages scroll past in a console window. This is normal.
4. When it's ready, **two new PowerShell windows** will open — one for the backend (port 8012) and one for the frontend (port 5175). Leave both windows open while you're using the app.
5. Open your browser to <http://localhost:5175> and log in with the username and password you set in `.env`.

To stop the app, close both of the new PowerShell windows.

## Day-to-day use

Just right-click `start.ps1` → **Run with PowerShell** whenever you want to use the app. After the first run it's quick — usually under 10 seconds before the windows open.

## Where your data lives

All your transactions are stored in a file called `credit_tracker.db` in the project folder. This file is yours and only yours — copy it somewhere safe (OneDrive, an external drive, etc.) to back up your data.

## Troubleshooting

**"Running scripts is disabled on this system"**

Windows blocks PowerShell scripts by default. To allow them:

1. Open PowerShell **as Administrator** (search Start menu for "PowerShell", right-click → **Run as administrator**).
2. Run:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

3. Answer `Y` when prompted.
4. Close the Administrator window and try `start.ps1` again.

**"Could not find npm"**

Node.js isn't installed (or isn't on your system PATH). Install Node.js LTS from <https://nodejs.org> using the default options, then restart PowerShell and try again.

**"ADMIN_USERNAME and ADMIN_PASSWORD must be set"**

You haven't filled in your credentials yet. Open `backend\.env` in Notepad and add a username and password after the `=` signs, then save and re-run `start.ps1`. See **First-time setup** above.

**The browser shows "This site can't be reached"**

The servers haven't finished starting up yet — wait 5–10 seconds and refresh the page. If the two PowerShell windows have closed unexpectedly, run `start.ps1` again.

**I forgot my password**

Close the two app PowerShell windows, then delete `credit_tracker.db` from the project folder, edit `backend\.env` with new credentials, and run `start.ps1` again. **Warning:** this wipes your transactions too. Back up the `.db` file first if you want to keep your data and ask a developer for help resetting the password.

**A previous run is "still using" port 8012 or 5175**

The start script tries to kill old instances automatically. If that ever fails, restart your computer — it's the simplest way to free the ports.
