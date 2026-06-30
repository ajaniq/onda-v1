# ONDA — Changelog & Feature Notes

This file tracks new/changed features and, importantly, **how each change affects other
features' behavior** (cross-feature impacts). Newest first.

---

## Batch 3 — UX fixes & navigation

### Fixed
- **Genre dropdown didn't apply.** Picking a genre from the ▾ menu updated the data but
  the row's text box still showed the old value, so it looked like nothing changed. The
  row now re-renders on pick. *(`pickGenre` → `render()`)*
- **Send → USB used the old genre / lost its USB badge.** If you typed a genre and
  immediately hit ▸ USB, the genre save was still in flight, so the file landed in the
  old genre folder (or got skipped). A **save-flush** now runs before any USB send, so
  pending tag edits are committed first.
  - Cross-feature: introduced `flushSaves()` + in-flight tracking (`INFLIGHT`,
    `PENDING_TRACKS`). `doSave` is now a thin wrapper over `_doSave`. Any future action
    that depends on edits being persisted should `await flushSaves()` first.
  - Backend note: `save_track` already preserves `usb`/`usb_genre` (it merges only
    whitelisted fields into the server's copy), so a late edit can't wipe a USB badge.
- **Rows stayed dimmed after the tutorial.** The walkthrough's spotlight class is now
  cleared defensively from *all* elements on every step and on exit (not just the last
  tracked one), and the tip's transform is reset.

### Added
- **Back / Forward view history** (‹ › buttons in the header). Steps through *view* state
  only: selected folder, search text, sidebar filters (genre/key/tags/energy/BPM/rating),
  sort, show-hidden/selected, and active USB. History is captured (debounced) at the end
  of `render()`.
  - Cross-feature: this is **separate from Undo/Redo**. Undo/Redo = data/file changes;
    Back/Forward = where you were looking. Restoring a view does **not** re-scan folders;
    it re-applies filters to whatever library is loaded.
- **USB progress bar** in the toolbar — shows how many library tracks are on the active
  USB (e.g. `42/310 on USB-1`). Updates on render and on selection/count changes.
  Depends on `t.usb === ACTIVE_USB`.
- **Resizable columns** — drag the right edge of any column header. Widths persist in
  `localStorage['djlib-colw']`. New **Reset cols** button clears them.
  - Cross-feature: table now renders a `<colgroup>`; the resize handle stops click
    propagation so it won't trigger a column sort.
- **Spacebar = play/pause** when the ONDA window is focused and you're not typing in a
  field or inside an open modal.

### Changed
- **Search box placeholder** simplified to just `Search…`. All advanced filters still
  work (`genre:`, `artist:`, `bpm:120-128`, etc.) and are documented in the box's tooltip.
- **Sidebar collapse arrows** enlarged (9px → 13px) with an accent hover color.

---

## Batch 2 — search, undo/redo, player

### Added
- **Smart search**: multi-word AND across all fields, field filters
  (`genre: artist: title: key: tag: bpm: energy: rating: notes:`, plus short aliases),
  numeric ranges (`bpm:120-130`, `bpm:>124`, `energy:7-9`), typo tolerance (fuzzy match),
  and an autocomplete dropdown.
- **Redo** (↪) alongside Undo. Undo/redo now covers every mutating action including
  **deleting a crate** and adding crates/sub-folders (which also clean up folders they
  created on undo).
  - Cross-feature: backend undo entries changed shape to
    `{before, after, moves:[[new,old]], copies:[[src,dst]], dirs:[…], touched, label}`.
    Any new mutating endpoint should `push_undo(snap, …, after=lib)` and return
    `can_undo`/`can_redo`.

### Fixed
- **Player seek desync** — added a `SEEKING` guard so the progress thumb no longer fights
  you while scrubbing; position commits on release.
- **Play/pause icon centering** — switched to inline SVG icons in a flex-centered button.
- **Text selection in edit fields** — clicking into a title/artist field no longer starts
  a row drag; grabbing elsewhere on the row still drags (and drags the whole selection).

---

## Conventions to keep in mind
- Only **crates** and the **USB box** accept track drops.
- Never commit the user's `music_library.json`; never delete user music.
- `app.html` changes take effect on page reload; `music_library.py` changes need an app
  restart.
