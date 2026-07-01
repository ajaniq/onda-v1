# ONDA — Changelog & Feature Notes

This file tracks new/changed features and, importantly, **how each change affects other
features' behavior** (cross-feature impacts). Newest first.

---

## Batch 12 — genre Enter + release readiness

- **Enter commits a genre** in the genre cell (works with the autocomplete list): pressing
  Enter applies the typed/selected genre and refreshes the row, matching the ▾-picker.
- Final front-end + back-end review before first package (see notes) — no blockers found.

---

## Batch 11 — render is the bottleneck (why buttons were slow)

Root cause: nearly every button calls `render()`, and `render()` had two hidden costs that
scale badly with library size — so every button got slow, not just scanning.

- **`render()` was O(n²).** It called `TRACKS.indexOf(t)` for every row (a linear scan per
  row). Replaced with an O(1) `path → index` map (`TIdx`). This is the big one.
- **The filter read the DOM once *per track*.** `passes()` called `checkedVals()`
  (`querySelectorAll`) ×3 and `num()` (`getElementById`) ×4 for every track — tens of
  thousands of DOM queries per render. Now the filter controls are read once into a context
  object and reused across all tracks.
- **Autocomplete value lists cached** — `_libValues` no longer rebuilds a set over all tracks
  on every keystroke; cached per field and cleared when data changes.
- **`content-visibility:auto` on rows** (`contain-intrinsic-size:auto 56px`) — the browser
  skips layout/paint for off-screen rows. Progressive enhancement; a no-op where unsupported.

Net: a single `render()` went from O(n²) + O(n×DOM) to O(n), so Show hidden / Reset cols /
filters / toggles are all fast now. (Reset cols still calls render, but render itself is cheap.)

---

## Batch 10 — front-end performance (large libraries)

- **Selection is O(changed), not O(all rows).** `rowCheck` now updates only the checkboxes
  that actually changed instead of scanning every row in the DOM. `updateCount` uses the
  already-computed `CURRENT_ROWS.length` instead of re-running the search/filter predicate
  over every track on each click. A `path -> track` index (`TByPath`) replaces repeated
  O(n) `TRACKS.find` / `new Map(...)` calls (used by the USB progress bar and send-to-USB).
- **Search is debounced** (~140ms) so typing doesn't rebuild thousands of rows per keystroke.

Still the biggest lever for very large libraries: **row virtualization** (render only the
rows near the viewport). Proposed, not yet implemented — it's the real fix for full re-render
cost on send/scroll but is a larger, higher-risk change.

---

## Batch 9 — backend performance

Behavior-preserving:
- **Parallel tag reads during scan** — `scan_folder` overlaps mutagen reads across a small
  thread pool (I/O-bound). Same library out; big win when adding large folders.
- **Cover-art cache** — `get_cover` caches extracted artwork by `(path, mtime, size)`
  (LRU 128), so re-renders/re-scrolls don't re-open and re-parse files. Identical bytes.
- **`all_tracks` single pass**; **`reconcile_usb`** hoisted `abspath(base)` out of the walk.

Approved architectural changes (A + B + E):
- **A — In-memory canonical library.** The JSON is parsed once at startup and kept in RAM
  as the source of truth (all routes run under `LIB_LOCK`). Removes a full disk-read +
  JSON-parse from every API call. Undo/redo now deep-copy their snapshots before making
  them canonical, so history can never be corrupted by later edits.
  *Trade-off:* the running app is authoritative over `music_library.json`; external edits
  to that file while ONDA is open are ignored until restart.
- **B — Write-behind saves.** Saves are debounced (~0.8s) and coalesced into a single disk
  write; a burst of tag edits becomes one write. Flushed on exit (atexit + shutdown) and
  available synchronously via `save_library(lib, immediate=True)`.
  *Trade-off:* a hard crash (not a clean quit) within the ~0.8s window could lose the last
  index change — tags are still embedded in the files themselves, and a rescan rebuilds it.
- **E — Compact on-disk JSON** (`separators=(",",":")`) — smaller file, faster read/write.
  *Trade-off:* the file is no longer pretty-printed. `json.load` still reads old files.

Deferred (still need approval): C — partial API payloads (touches `app.html`); D — moving
the missing-file prune off the per-request path (changes when deleted rows disappear).

---

## Batch 8 — toggle buttons, unhide all, sticky headers (real fix)

### Changed
- **Toggle controls are now buttons** — "Select all shown", "Show selected", "Show hidden"
  (toolbar) and "Only genres on active USB" (sidebar) are buttons styled like the others;
  when active they highlight with an accent border (`.tgl.on`). Uses theme variables, so it
  adapts to every theme.
  - Cross-feature: state now lives in JS vars (`SHOW_HIDDEN`, `SHOW_SELECTED`,
    `GENRE_USB_ONLY`) reflected onto the buttons via `_setTgl`; `updateSelAllBtn()` keeps
    "Select all shown" lit when every visible row is selected. View history restore and
    Clear filters update the button states too.

### Added
- **Unhide all** — toolbar button to unhide every hidden track at once.

### Fixed
- **Sticky headers (actually sticky now)** — the real culprit was `border-collapse:collapse`,
  which disables `position:sticky` on `<th>` in the macOS WKWebView. Switched the table to
  `border-collapse:separate; border-spacing:0`, removed a conflicting duplicate `th` rule,
  and pinned `thead th` to `top:var(--toolbarH)` (measured after each render / on resize).
  Column headers now stay on screen while scrolling.

---

## Batch 7 — player, headers, tutorial, drag clarity

### Fixed
- **Seek dot alignment** — replaced the native range input with a custom track + fill +
  thumb (`pbSeekDown`/`_pbSetPct`). The dot now sits exactly on the line at every position,
  in every engine; click or drag to seek, still guarded by `SEEKING`.
- **Tutorial reopened every launch** — the "seen it" flag now lives in the library JSON
  (`welcomed`, via `/api/set_welcomed`) so it survives restarts even when the webview's
  localStorage resets. Falls back to the old localStorage flag for existing installs.

### Added
- **Hide selected** — toolbar button hides every selected track at once.
- **Group-drag count badge** — dragging a multi-selection shows a "N tracks" chip as the
  drag image, and the selected rows tint while dragging, so it's clear what's moving.
- **Sticky table headers** — column headers (Art, BPM, Rating, …) stay pinned while you
  scroll. They sit just under the toolbar; the offset (`--toolbarH`) is measured after each
  render and on resize so it stays correct even when the toolbar wraps.
- **Collapsible cleanup suggestions** — in Clean genres, the "Suggested cleanups (N)" list
  collapses/expands via its header.
- **Only genres on active USB** — sidebar toggle filters the genre list to genres that have
  tracks on the active USB. Autocomplete/datalist still uses the full genre list.

### Changed
- Removed the 🧹 emoji from the **Clean genres…** button.

---

## Batch 6 — export, bulk genre, faster updates, backend reorg

### Added
- **Export many folders → one flat folder** — in the folder manager (`⋯`), select folders
  and hit **Export**; all their tracks are copied into one folder you pick, ready to drop
  into Serato/rekordbox. Flat layout (no subfolders), via `/api/export_folders`.
- **Bulk set genre** — a **Set genre…** toolbar button applies one genre to every selected
  track in a single undoable action (`/api/set_genre_bulk`). Pairs with "Select all shown".
  Flushes pending edits first (same guard as Send → USB).

### Changed
- **Folder manager matches the genre sidebar** — click to select, Shift-click for a range,
  highlight instead of checkboxes, footer actions **Export · Remove · Clear**.
- **Faster auto-update (less need for Rescan)** — `crate_drop` now runs `reconcile_usb`, so
  dropping a song into a crate that lives on a USB shows the `▸ USB / folder` badge
  immediately. Genre edits already refresh the sidebar live.
  - Cross-feature: any path that moves/copies files into a USB-backed location should call
    `reconcile_usb(lib)` before saving so membership stays live.

### Confirmed
- **Undo for deleting a genre** works (single via the ✕, and group via the sidebar bar);
  both push an undo entry that restores the cleared genres and re-embeds tags. Toasts now
  say "↩ to undo".

### Backend
- **`music_library.py` reorganized into 11 labeled sections** with a table of contents at
  the top (search `§1`…`§11`). No code split — same single file, same launcher/build — but
  a dev can jump straight to, e.g., `§6 USB FILING & CRATES`. Verified the module imports
  cleanly with all routes intact.

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
