# ONDA — Changelog & Feature Notes

This file tracks new/changed features and, importantly, **how each change affects other
features' behavior** (cross-feature impacts). Newest first.

---

## Batch 5 — rows, crates, group actions, duplicates

### Added
- **Row numbers** — a `#` column shows each track's position in the current view (updates
  with sort/filter/search) so you can see how far down you are.
- **Drag a folder onto Crates** — the Crates area is now a drop zone. Because the webview
  sandbox hides a dropped folder's real path (unlike a native app such as Serato), the
  drop opens the folder picker to confirm which folder to add as a crate.
  - Cross-feature: existing track-onto-crate drops still work; the crate/USB drop handlers
    now bail on OS file drags so they bubble to the zone handler.
- **Group-select & delete genres (sidebar)** — click a genre to select, Shift-click for a
  range; a bar shows "N selected · Delete · Clear". Deletes all selected genres in one
  undoable action (`/api/delete_genres`). The per-genre ✕ and the filter checkbox are
  unchanged and independent of selection.
- **Group-remove folders** — a `⋯` button by the Folder dropdown opens a manager: check
  folders (Shift-click for a range) and Remove selected in one undoable action
  (`/api/remove_sources`).
- **Duplicate-on-USB detection** — when you add/scan a folder, ONDA reconciles it against
  your USBs; tracks already on the **active** USB keep their `▸ USB / genre` badge (the
  "row badge"), and a **toast** (the small temporary message at the bottom) reports e.g.
  "12 already on USB-1". *(A "count toast" = that bottom notification; a "row badge" = the
  little ▸ label on the track row.)*

### Changed
- **Crate folders are hidden** from the top **Folder** dropdown (they belong in the Crates
  sidebar). Applies to exact crate paths and anything nested under them.
  - Cross-feature: `renderSrcBar()` and the folder manager share the same crate-filter.

---

## Batch 4 — player, progress, genre & rescan

### Fixed
- **Spacebar didn't always pause.** It now toggles play/pause even when a button has
  focus (e.g. right after clicking ▶); only real text fields (`input`/`select`/`textarea`/
  contenteditable) and open modals are excluded. A focused button is blurred after toggling.
- **Seek thumb (circle) misaligned with the blue line.** Added
  `-webkit-slider-runnable-track` / `-moz-range-track` rules and a `margin-top` on the
  thumb so the 12px circle sits centered on the 4px fill line.

### Added
- **Progress bar now reflects the rows shown.** Denominator is the count of currently
  visible rows (after filters/search), numerator is how many of those are on the active
  USB — so it tracks whatever you're looking at, not the whole library.
  - Cross-feature: `updateUsbProgress()` now reads `CURRENT_ROWS` (set in `render()`),
    so it stays correct under search/filter/source changes.
- **Genre autocomplete** while typing in a genre cell — native dropdown of existing
  genres via a shared `<datalist id="genreOptions">` populated in `buildFilters()`.
- **Rescan reconciles USB membership.** `reconcile_usb()` walks each USB folder and
  marks/unmarks tracks by filename match, setting `usb_genre` from the sub-folder.
  - Cross-feature: only clears markers for **mounted** USBs (unplugged drive ≠ wiped
    membership). Feeds the genre USB dot, the row badge, and the progress bar. Runs at
    the end of `rescan_all`.

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
