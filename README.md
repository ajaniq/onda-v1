<img width="1024" height="1024" alt="ONDA_LOGOv2" src="https://github.com/user-attachments/assets/7cdebff5-7973-472d-8e86-f143171526b3" />
# ONDA

A local macOS app for DJs to tag, preview, and organize a music library, then
build genre-sorted "USB" crates for sets. Tags are saved into your files *and* a
local library, so other apps (Rekordbox / Serato / Traktor) can read them.

Everything runs on your Mac — no internet, no accounts, no uploads.

## Features

- Tag tracks: title (renames the file), artist, genre, energy, rating, tags,
  notes, and custom fields. BPM and key are read from the file.
- Camelot ⇄ standard key notation, colour-coded.
- Preview with a custom themed player (play/pause, seek, times).
- USB hubs: file tracks into `<USB>/<Genre>/` by Copy or Move; auto-file option.
- Crates: real folders (with sub-folders) you build by dragging tracks in.
- Genre cleanup: merge duplicate spellings (review-first; never collapses sub-genres).
- Cover art, bitrate flag (green ≥320k / red <320k), hide/show tracks, sortable
  columns, collapsible sidebar, Undo, 6 themes, first-run tutorial + Help.

## Run it (development)

Requires Python 3 (ships with macOS / install from python.org).

```bash
python3 -m pip install --user mutagen pywebview   # one time
python3 music_library.py
```

It starts a tiny local server and opens a window (native via pywebview, or a
browser tab as fallback). Keep the terminal open while using it.

### Live-editing loop

The server serves `app.html` fresh on every page load, so:

- Edit **`app.html`** (the entire UI/JS) → just **reload the window/page** to see changes. No restart, no rebuild.
- Edit **`music_library.py`** (the backend) → stop with `Ctrl+C` and run it again.

Tip: for fast front-end work, open the printed `http://127.0.0.1:PORT/` URL in a
normal browser tab and use its reload button. To force the browser path instead
of the native window, run: `DJLIB_UI=chrome python3 music_library.py`.

## Build a standalone app (to share)

`Build ONDA (standalone).command` produces a self-contained `ONDA.app` (bundles
Python + deps) using PyInstaller. See `HOW TO SHARE ONDA.md`.

## Project structure

| File | What it is |
|------|------------|
| `music_library.py` | Backend: local HTTP server + tag/USB/crate logic |
| `app.html` | The entire front-end (UI + JavaScript), served by the backend |
| `logo.png` / `icon.icns` | App logo and macOS icon |
| `Start Music Library.command` | Double-click launcher (dev / lightweight use) |
| `Build ONDA (standalone).command` | One-shot standalone build script |
| `HOW TO SHARE ONDA.md` | Distribution + Gatekeeper notes |

## Where your data lives

`~/Library/Application Support/ONDA/music_library.json` — outside the app, so
updates never lose your library. (Git-ignored; never committed.)

## License

MIT 
