# Sharing ONDA with other Mac users

The easiest thing to send anyone is the **standalone** build — a single app that
needs no Python, no pip, and no internet.

## Option A — Standalone app (recommended for sharing)

A self-contained `ONDA.app` that bundles Python and everything it needs. The
person you send it to just double-clicks.

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
> same chip runs it natively; the other type runs it via Rosetta. If you want one
> app that runs natively on both, that's a "universal2" build — ask and I'll adjust
> the build command.

## Option B — Run from source (for yourself / technical friends)

Keep `music_library.py` and `app.html` together and either double-click
**`Start Music Library.command`** or run `python3 music_library.py`. This uses the
Mac's built-in Python and installs two small helpers (`mutagen`, `pywebview`) the
first time. Fine for you or a developer; for a non-technical person, prefer
Option A so they don't hit a "install developer tools" prompt.

## What everyone needs to know (both options)

Because the app isn't signed by Apple, macOS shows an **"unidentified developer"**
warning the first time. To open it:

- **Right-click `ONDA.app` → Open → Open.** (Do this once; afterward it opens normally.)
- On the newest macOS you may instead need: **System Settings → Privacy &
  Security → scroll down → "Open Anyway".**

## First run

- ONDA opens its own window and shows a short built-in tutorial (once).
- Click **Add Folder…** to load music — your files are only read, never changed,
  until you explicitly edit a tag or send to a USB.
- Sending to a USB **copies** by default (originals stay put); switch to **Move**
  in Settings if you prefer.

## Updating someone's app

Send a new `ONDA-standalone.zip` and have them replace the old `ONDA.app`. Their
library is safe — it lives in `~/Library/Application Support/ONDA/`, outside the
app, so replacing the app never touches it.

## Where ONDA stores data

Tags, USBs, and settings are saved in `~/Library/Application Support/ONDA/` —
outside the app — so updating or replacing the app never loses your library. Tags
are also embedded in the audio files themselves.
