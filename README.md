<img width="1024" height="1024" alt="ONDA_LOGOv2" src="https://github.com/user-attachments/assets/7cdebff5-7973-472d-8e86-f143171526b3" />

# ONDA

A local macOS app for DJs to tag, preview, and organize a music library, then
build genre-sorted "USB" crates for sets. Tags are saved into your files *and* a
local library, so other apps (Rekordbox / Serato / Traktor) can read them.

Everything runs on your Mac — no internet, no accounts, no uploads.

## Features

**Tagging**
- Edit title (renames the file), artist, genre, energy, rating, tags, notes, and
  your own custom fields. BPM and key are read from the file.
- Camelot ⇄ standard key notation, colour-coded.
- Genre autocomplete (type a genre and press Enter, or pick from the list).
- Bulk edits: set one genre across all selected tracks in a single undoable step.

**Find & organize**
- Smart search: multi-word matching across every field, field filters
  (`genre:` `artist:` `key:` `tag:` `bpm:` `energy:` `rating:` `notes:`), numeric
  ranges (`bpm:120-128`, `bpm:>124`), typo tolerance, and an autocomplete dropdown.
- Sidebar filters (genre / energy / rating / BPM / key / tags), shift-click to
  multi-select genres, and an "only genres on the active USB" toggle.
- Sortable, resizable columns (with Reset), row numbers, sticky headers, hide /
  show / unhide-all, and a collapsible sidebar.

**Preview**
- Custom themed player: play/pause, click-or-drag seek, elapsed/total times.
- **Spacebar** plays/pauses when the window is focused and you're not typing.

**USB crates & sets**
- File tracks into `<USB>/<Genre>/` by Copy or Move; optional auto-file on tagging.
- USB membership is detected automatically on rescan; a progress bar shows how much
  of the current view is already on the active USB, and newly-added folders flag
  songs that are already on it.
- Crates: real folders (with sub-folders) built by dragging tracks in — drag a
  whole multi-selection at once. Drop a folder onto the Crates area to add it.
- Export one or more folders into a single flat folder, ready for Serato/rekordbox.

**Cleanup & history**
- Genre cleanup: review-first merging of duplicate spellings (never collapses
  sub-genres); suggestions are collapsible. Group-delete genres or folders.
- **Undo and Redo** for every change; **Back / Forward** to step through views.

**Comfort**
- Cover art, bitrate flag (green ≥320k / red <320k), multiple colour themes, and a
  first-run tutorial + Help that remembers it's been seen.

**Built for large libraries** — selecting, filtering, and sending stay fast into
the thousands of tracks (in-memory library, debounced saves, O(n) rendering).

## Run it (development)

Requires Python 3 (ships with macOS / install from python.org).

```bash
python3 -m pip install --user mutagen pywebview   # one time
python3 music_library.py
```

It starts a tiny local server and opens a window (native via pywebview, or a
browser tab as fallback). Keep the terminal open while using it. Or just
double-click **`Start Music Library.command`**.

### Live-editing loop

- Edit **`app.html`** (the entire UI/JS) → **reload the window/page**. No restart.
- Edit **`music_library.py`** (the backend) → stop with `Ctrl+C` and run it again.

Tip: for fast front-end work, open the printed `http://127.0.0.1:PORT/` URL in a
normal browser tab. To force the browser path instead of the native window:
`DJLIB_UI=chrome python3 music_library.py`.

## Build a standalone app (to share)

`Build ONDA (standalone).command` produces a self-contained `ONDA.app` (bundles
Python + deps) using PyInstaller. See `HOW TO SHARE ONDA.md`.

## Project structure

| File | What it is |
|------|------------|
| `music_library.py` | Backend: local HTTP server + tag/USB/crate logic (organized into labeled `§` sections) |
| `app.html` | The entire front-end (UI + JavaScript), served by the backend |
| `logo.png` / `icon.icns` | App logo and macOS icon |
| `Start Music Library.command` | Double-click launcher (dev / lightweight use) |
| `Build ONDA (standalone).command` | One-shot standalone build script |
| `HOW TO SHARE ONDA.md` | Distribution + Gatekeeper notes |
| `CHANGELOG.md` | Per-release notes and cross-feature impacts |

## Where your data lives

`~/Library/Application Support/ONDA/music_library.json` — outside the app, so
updates never lose your library. (Git-ignored; never committed.)

While ONDA is running it treats that file as the source of truth and saves changes
back to it a moment after you make them (so a burst of edits is one write). Your
actual tags are also written into the audio files themselves.

## License

MIT
