# Sharing ONDA with other Mac users

You have two ways to distribute ONDA. For sending it to friends/anyone, use the
**standalone** build.

## Option A — Standalone app (recommended for sharing)

A self-contained `ONDA.app` that bundles Python and everything it needs. The
person you send it to just double-clicks — **no Python, no pip, no internet.**

### Build it (one time, on your Mac)

1. Put these files together in one folder:
   `music_library.py`, `app.html`, `logo.png`, `icon.icns`, and
   `Build ONDA (standalone).command`.
2. Right-click **`Build ONDA (standalone).command`** → **Open** → **Open**
   (first time only — it's an unsigned script).
3. Wait ~1–2 minutes. When it finishes, a `dist` folder opens containing:
   - **`ONDA.app`** — the finished standalone app
   - **`ONDA-standalone.zip`** — the same app, zipped for sending

Send the `.zip`. That's it.

> The app is built for your Mac's chip (Apple Silicon or Intel). A Mac with the
> same chip type runs it natively; the other type runs it via Rosetta. If you
> want one app that runs natively on both, that's a "universal2" build — ask and
> I'll adjust the command.

## Option B — Lightweight (smaller, needs Python)

`ONDA.zip` is the small version: it uses the Mac's built-in Python and installs
two helpers on first launch. Good for yourself or technical friends, but a
non-technical person may hit a "install developer tools" prompt. For general
sharing, prefer Option A.

## What everyone needs to know (both options)

Because the app isn't signed by Apple, macOS shows an **"unidentified developer"**
warning the first time. To open it:

- **Right-click `ONDA.app` → Open → Open.** (Do this once; afterward it opens normally.)
- On the newest macOS you may instead need: **System Settings → Privacy &
  Security → scroll down → "Open Anyway".**

## Removing the warning entirely (optional)

To let anyone open it with a normal double-click (no warning), the app must be
**code-signed and notarized** by Apple. That requires an **Apple Developer
account ($99/year)**. If you want to go that route, I can walk you through:
`codesign` → `xcrun notarytool submit` → `xcrun stapler staple`.

## Where ONDA stores data

Tags, USBs, and settings are saved in `~/Library/Application Support/ONDA/` —
outside the app — so updating or replacing the app never loses your library.
