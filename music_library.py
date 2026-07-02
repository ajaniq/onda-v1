#!/usr/bin/env python3
"""DJ Music Library - local web app backend (tagging, USB hubs, cover art,
bitrate, Camelot keys, undo). See README. Start: python3 music_library.py

================================================================================
 ONDA BACKEND - TABLE OF CONTENTS
================================================================================
 To change a behavior, jump to its section (search for the §N banner):

   §1  PATHS & CONSTANTS .......... where files live, audio extensions, globals
   §2  LIBRARY STORE .............. load/save the JSON library, safe filenames
   §3  GENRE NORMALIZATION ........ aliases, canonical names, fuzzy matching
   §4  UNDO / REDO ................ the undo & redo stacks + push_undo()
   §5  FILE TAGS & COVER ART ...... read/write ID3-MP4-Vorbis tags, cover images
   §6  USB FILING & CRATES ........ send-to-USB, reconcile membership, crate tree
   §7  SCANNING & TRACK BUILDING .. walk folders, build track records
   §8  CUSTOM FIELDS .............. user-defined columns <-> embedded struct
   §9  NATIVE DIALOGS & EXPORT .... folder pickers, text prompts, flat export
   §10 HTTP SERVER & API ROUTES ... the Handler class; one _route_api_* per call
   §11 SERVER BOOTSTRAP / main() .. port pick, native window, startup
================================================================================
"""

import os, re, sys, copy, json, uuid, shutil, socket, atexit, mimetypes, subprocess, threading, webbrowser, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

# ============================================================================
# §1  PATHS & CONSTANTS
# ============================================================================

def script_dir():
    return os.path.dirname(os.path.abspath(__file__))

def resource_dir():
    """Where app.html / logo.png live (handles PyInstaller-frozen apps too)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _data_dir():
    """Persistent location for the library so USBs/tags survive app updates."""
    base = os.path.expanduser("~/Library/Application Support/ONDA")
    try:
        os.makedirs(base, exist_ok=True)
        return base
    except Exception:
        return script_dir()

LIBRARY_PATH = os.path.join(_data_dir(), "music_library.json")
APP_HTML_PATH = os.path.join(resource_dir(), "app.html")

# one-time migration: if an older library lived next to the app, bring it over
_OLD_LIBRARY = os.path.join(script_dir(), "music_library.json")
if not os.path.exists(LIBRARY_PATH) and os.path.exists(_OLD_LIBRARY):
    try:
        shutil.copy2(_OLD_LIBRARY, LIBRARY_PATH)
    except Exception:
        pass
AUDIO_EXTS = (".mp3", ".m4a", ".aiff", ".aif", ".flac", ".wav", ".ogg", ".aac", ".wma", ".alac", ".m4b")
LOSSLESS_EXTS = (".flac", ".wav", ".aif", ".aiff", ".alac")
DJLIB_MARKER = "DJLIB|"
LIB_LOCK = threading.Lock()
UNDO = []
REDO = []
UNDO_MAX = 40

# ============================================================================
# §2  LIBRARY STORE  (load/save the JSON library on disk; safe filenames)
# ============================================================================
def default_library():
    return {"folder": "", "sources": [], "fields": [], "tracks": {}, "usbs": [], "active_usb": "",
            "auto_file": False, "usb_mode": "copy", "crate_base": "", "crates": [], "welcomed": False}

# In-memory canonical library: parse the JSON once, then keep it in RAM as the source
# of truth while running. Every route already runs under LIB_LOCK, so this is safe and
# removes a full disk-read + JSON-parse from every API call. Persistence is write-behind
# (debounced + coalesced) so a burst of edits becomes a single disk write; a flush runs
# on exit. On-disk JSON is compact (smaller file -> faster to read/write/parse).
_LIB = None
_DIRTY = False
_SAVE_TIMER = None
_SAVE_DELAY = 0.8   # seconds

def load_library():
    global _LIB
    if _LIB is None:
        lib = default_library()
        if os.path.exists(LIBRARY_PATH):
            try:
                with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k in lib:
                    if k in data:
                        lib[k] = data[k]
            except Exception:
                pass
        _LIB = lib
    return _LIB

def _write_library_to_disk(lib):
    tmp = LIBRARY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, LIBRARY_PATH)

def _flush_locked():
    """Persist if dirty. Assumes the caller already holds LIB_LOCK."""
    global _DIRTY, _SAVE_TIMER
    if _SAVE_TIMER is not None:
        _SAVE_TIMER.cancel(); _SAVE_TIMER = None
    if _DIRTY and _LIB is not None:
        _write_library_to_disk(_LIB)
        _DIRTY = False

def _flush_from_timer():
    global _SAVE_TIMER
    with LIB_LOCK:
        _SAVE_TIMER = None
        try:
            _flush_locked()
        except Exception:
            pass

def flush_library():
    """Force a synchronous persist now (acquires LIB_LOCK). For atexit / shutdown."""
    with LIB_LOCK:
        _flush_locked()

def save_library(lib, immediate=False):
    """Update the canonical library and schedule a debounced disk write.
    Routes call this while holding LIB_LOCK; pass immediate=True to write synchronously
    within that locked section (do NOT call flush_library() from inside the lock)."""
    global _LIB, _DIRTY, _SAVE_TIMER
    _LIB = lib
    _DIRTY = True
    if immediate:
        _flush_locked(); return
    if _SAVE_TIMER is None:
        _SAVE_TIMER = threading.Timer(_SAVE_DELAY, _flush_from_timer)
        _SAVE_TIMER.daemon = True
        _SAVE_TIMER.start()

def safe_name(name):
    return re.sub(r'[<>:"/\\|?*]', "_", (name or "").strip()).strip() or "Untitled"

# ---- genre normalization (alias-based; never collapses sub-genres) ----
# variant (normalized) -> canonical normalized key. Only unambiguous synonyms.
# ============================================================================
# §3  GENRE NORMALIZATION  (aliases, canonical display names, fuzzy matching)
# ============================================================================
GENRE_ALIASES = {
    "dnb": "drum and bass", "d n b": "drum and bass", "drum n bass": "drum and bass",
    "drum bass": "drum and bass",
    "hiphop": "hip hop",                       # NOTE: 'rap' is intentionally NOT mapped here
    "rnb": "r and b", "r n b": "r and b", "rhythm and blues": "r and b",
    "ukg": "uk garage",
    "nudisco": "nu disco",
    "electronica": "electronic",               # Electronic + Electronica only (not EDM/Dance)
}
# curated "pretty" display for known canonical keys (suggested, still editable)
CANONICAL_DISPLAY = {
    "hip hop": "Hip-Hop", "drum and bass": "Drum & Bass", "r and b": "R&B",
    "uk garage": "UK Garage", "nu disco": "Nu Disco", "electronic": "Electronic",
    "house": "House", "deep house": "Deep House", "tech house": "Tech House",
    "bass house": "Bass House", "future house": "Future House", "afro house": "Afro House",
    "progressive house": "Progressive House", "techno": "Techno", "melodic techno": "Melodic Techno",
    "minimal": "Minimal", "trance": "Trance", "psytrance": "Psytrance",
    "dubstep": "Dubstep", "trap": "Trap", "garage": "Garage", "grime": "Grime",
    "disco": "Disco", "funk": "Funk", "soul": "Soul", "jazz": "Jazz", "pop": "Pop",
    "rock": "Rock", "indie": "Indie", "hyperpop": "Hyperpop", "dance pop": "Dance Pop",
    "edm": "EDM", "dance": "Dance", "amapiano": "Amapiano", "afrobeats": "Afrobeats",
    "reggaeton": "Reggaeton", "hardstyle": "Hardstyle", "hardcore": "Hardcore",
    "breakbeat": "Breakbeat", "ambient": "Ambient", "reggae": "Reggae", "dancehall": "Dancehall",
}
def _norm_genre(g):
    s = (g or "").strip()
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)   # split camelCase: JerseyClub -> Jersey Club
    s = s.lower()
    s = re.sub(r"\([^)]*\)", " ", s)   # drop "(ish)", "(clean)", "(original mix)" etc.
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[._/+\-]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s in GENRE_ALIASES:
        return GENRE_ALIASES[s]
    ns = s.replace(" ", "")          # also match acronyms that got split (DnB -> dn b -> dnb)
    if ns in GENRE_ALIASES:
        return GENRE_ALIASES[ns]
    return s
def _tidy_genre(s):
    """Title-case + use & ; for genres without a curated name."""
    s = re.sub(r"\s+", " ", (s or "").strip())
    words = [w if (w.isupper() and len(w) <= 4) else w.capitalize() for w in s.split(" ")]
    out = " ".join(words)
    return re.sub(r"\bAnd\b", "&", out)
def _canonical_display(normkey, members=None):
    if normkey in CANONICAL_DISPLAY:
        return CANONICAL_DISPLAY[normkey]
    return _tidy_genre(normkey)   # build a clean name from the normalized key
def _lev(a, b):
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 1:
        return 2
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[len(b)]

# ============================================================================
# §4  UNDO / REDO  (snapshot-based; each entry stores before/after + file ops)
# ============================================================================
def push_undo(snapshot, moves, touched, label, copies=None, after=None, dirs=None):
    # moves: [[new, old]...]  copies: [[src, dst]...]  dirs: [created dirs]
    UNDO.append({"before": snapshot, "after": copy.deepcopy(after) if after is not None else None,
                 "moves": moves or [], "copies": copies or [], "touched": touched or [],
                 "dirs": dirs or [], "label": label})
    REDO.clear()
    while len(UNDO) > UNDO_MAX:
        UNDO.pop(0)

def _norm_copies(copies):
    # accept legacy [dst] or new [src,dst]; return [src,dst] (src may be None)
    out = []
    for c in (copies or []):
        if isinstance(c, (list, tuple)):
            out.append([c[0], c[1]] if len(c) > 1 else [None, c[0]])
        else:
            out.append([None, c])
    return out

# ============================================================================
# §5  FILE TAGS & COVER ART  (read/write ID3 / MP4 / Vorbis; embedded cover)
# ============================================================================
def _require_mutagen():
    try:
        import mutagen  # noqa
    except ImportError:
        raise RuntimeError("The 'mutagen' library is required: python3 -m pip install --user mutagen")

def _parse_comment(comment):
    notes, struct = comment or "", {}
    if comment and DJLIB_MARKER in comment:
        before, after = comment.split(DJLIB_MARKER, 1)
        notes = before.strip()
        for part in after.strip().split("|"):
            if "=" in part:
                k, v = part.split("=", 1)
                struct[k.strip()] = v.strip()
    return notes, struct

def _build_comment(notes, struct):
    pieces = []
    for k, v in struct.items():
        if v not in (None, "", []):
            if isinstance(v, list):
                v = ",".join(str(x) for x in v)
            pieces.append(f"{k}={v}")
    out = (notes or "").strip()
    if pieces:
        if out:
            out += "\n"
        out += DJLIB_MARKER + "|".join(pieces)
    return out

def read_file_tags(path):
    _require_mutagen()
    import mutagen
    info = {"artist": "", "genre": "", "bpm": "", "key": "", "comment": "",
            "bitrate": 0, "lossless": os.path.splitext(path)[1].lower() in LOSSLESS_EXTS}
    try:
        easy = mutagen.File(path, easy=True)
        if easy is not None and easy.tags is not None:
            def g(k):
                v = easy.tags.get(k)
                if isinstance(v, list) and v:
                    return str(v[0]).strip()
                return str(v).strip() if v else ""
            info["artist"] = g("artist")
            info["genre"], info["bpm"] = g("genre"), g("bpm")
    except Exception:
        pass
    try:
        raw = mutagen.File(path)
        if raw is not None:
            if getattr(raw, "info", None) is not None:
                br = getattr(raw.info, "bitrate", 0) or 0
                info["bitrate"] = int(round(br / 1000.0)) if br else 0
            if raw.tags is not None:
                tags, cls = raw.tags, raw.__class__.__name__
                if hasattr(tags, "getall"):
                    comm = tags.getall("COMM")
                    if comm:
                        info["comment"] = str(comm[0].text[0]) if comm[0].text else ""
                    tkey = tags.get("TKEY")
                    if tkey:
                        info["key"] = str(tkey.text[0]) if tkey.text else ""
                    if not info["bpm"]:
                        tbpm = tags.get("TBPM")
                        if tbpm:
                            info["bpm"] = str(tbpm.text[0]) if tbpm.text else ""
                    # WAV/AIFF: the 'easy' reader above doesn't expose these, so read the
                    # raw ID3 frames as a fallback (harmless for MP3, which already has them).
                    if not info["genre"]:
                        tcon = tags.get("TCON")
                        if tcon and tcon.text:
                            info["genre"] = str(tcon.text[0])
                    if not info["artist"]:
                        tpe1 = tags.get("TPE1")
                        if tpe1 and tpe1.text:
                            info["artist"] = str(tpe1.text[0])
                elif cls in ("MP4", "M4A", "AAC"):
                    if "\xa9cmt" in tags:
                        info["comment"] = str(tags["\xa9cmt"][0])
                    for kk in ("----:com.apple.iTunes:initialkey", "----:com.apple.iTunes:KEY", "----:com.apple.iTunes:Key"):
                        if kk in tags:
                            val = tags[kk][0]
                            info["key"] = val.decode("utf-8", "ignore") if isinstance(val, bytes) else str(val)
                            break
                else:
                    def vget(k):
                        v = tags.get(k)
                        if not v:
                            return ""
                        return str(v[0]) if isinstance(v, list) else str(v)
                    info["comment"] = vget("comment") or vget("description")
                    info["key"] = vget("initialkey") or vget("key")
                    if not info["bpm"]:
                        info["bpm"] = vget("bpm")
    except Exception:
        pass
    return info

def _repair_container(path):
    """Heal a WAV/AIFF that a prior version corrupted by prepending an ID3v2 tag
    to the front of the file (turning 'RIFF'/'FORM' into 'ID3...'). If the real
    container header sits right after a leading ID3 tag, strip the tag so the file
    is a valid RIFF/AIFF again. No-op for healthy files. Returns True if repaired."""
    try:
        with open(path, "rb") as f:
            head = f.read(10)
            if len(head) < 10 or head[:3] != b"ID3":
                return False
            size = (head[6] & 0x7f) << 21 | (head[7] & 0x7f) << 14 | (head[8] & 0x7f) << 7 | (head[9] & 0x7f)
            total = 10 + size + (10 if head[5] & 0x10 else 0)   # + optional footer
            f.seek(total)
            if f.read(4) not in (b"RIFF", b"FORM"):
                return False                                     # not our corruption; leave it alone
            f.seek(total)
            tmp = path + ".fixtmp"
            with open(tmp, "wb") as g:
                shutil.copyfileobj(f, g)
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            if os.path.exists(path + ".fixtmp"):
                os.remove(path + ".fixtmp")
        except Exception:
            pass
        return False

def _apply_id3_frames(tags, genre, artist, title, comment):
    from mutagen.id3 import COMM, TCON, TPE1, TIT2
    if genre is not None:
        tags.delall("TCON")
        if genre != "":
            tags.add(TCON(encoding=3, text=[genre]))
    if artist is not None:
        tags.delall("TPE1"); tags.add(TPE1(encoding=3, text=[artist]))
    if title is not None:
        tags.delall("TIT2"); tags.add(TIT2(encoding=3, text=[title]))
    tags.delall("COMM")
    if comment:
        tags.add(COMM(encoding=3, lang="eng", desc="", text=[comment]))

def write_file_tags(path, genre=None, notes=None, struct=None, artist=None, title=None):
    _require_mutagen()
    import mutagen
    from mutagen.id3 import ID3, ID3NoHeaderError
    ext = os.path.splitext(path)[1].lower()
    comment = _build_comment(notes or "", struct or {})
    try:
        if ext == ".mp3":
            try:
                tags = ID3(path)
            except ID3NoHeaderError:
                tags = ID3()
            _apply_id3_frames(tags, genre, artist, title, comment)
            tags.save(path)
            return True, "ok"
        if ext in (".wav", ".aiff", ".aif"):
            # WAV/AIFF are RIFF/FORM containers: the ID3 tag must live INSIDE a chunk,
            # never be prepended to the file (that corrupts the container and breaks
            # Serato/Rekordbox). Heal any previously-damaged file, then use the wrapper.
            _repair_container(path)
            if ext == ".wav":
                from mutagen.wave import WAVE
                audio = WAVE(path)
            else:
                from mutagen.aiff import AIFF
                audio = AIFF(path)
            if audio.tags is None:
                audio.add_tags()
            _apply_id3_frames(audio.tags, genre, artist, title, comment)
            audio.save()
            return True, "ok"
        audio = mutagen.File(path)
        if audio is None:
            return False, "unsupported format"
        cls = audio.__class__.__name__
        if cls in ("FLAC", "OggVorbis", "OggOpus", "OggFLAC"):
            if genre is not None:
                audio.pop("genre", None) if genre == "" else audio.__setitem__("genre", genre)
            if artist is not None:
                audio["artist"] = artist
            if title is not None:
                audio["title"] = title
            if comment:
                audio["comment"] = comment
            else:
                audio.pop("comment", None)
            audio.save(); return True, "ok"
        if cls in ("MP4", "M4A", "AAC"):
            if genre is not None:
                audio.pop("\xa9gen", None) if genre == "" else audio.__setitem__("\xa9gen", [genre])
            if artist is not None:
                audio["\xa9ART"] = [artist]
            if title is not None:
                audio["\xa9nam"] = [title]
            if comment:
                audio["\xa9cmt"] = [comment]
            elif "\xa9cmt" in audio:
                del audio["\xa9cmt"]
            audio.save(); return True, "ok"
        easy = mutagen.File(path, easy=True)
        if easy is not None:
            if genre is not None:
                easy.pop("genre", None) if genre == "" else easy.__setitem__("genre", genre)
            if artist is not None:
                easy["artist"] = artist
            if title is not None:
                easy["title"] = title
            try:
                easy["comment"] = comment
            except Exception:
                pass
            easy.save(); return True, "ok"
        return False, "unsupported format"
    except Exception as e:
        return False, str(e)

def get_cover(path):
    # Cache extracted artwork keyed by (mtime, size) so re-renders / re-scrolls don't
    # re-open and re-parse the same file. Identical bytes out; bounded memory.
    if not path:
        return None, None
    try:
        st = os.stat(path)
    except OSError:
        return None, None
    return _cover_cached(path, st.st_mtime_ns, st.st_size)

@lru_cache(maxsize=128)
def _cover_cached(path, _mtime, _size):
    return _extract_cover(path)

def _extract_cover(path):
    _require_mutagen()
    import mutagen
    try:
        raw = mutagen.File(path)
        if raw is None:
            return None, None
        if hasattr(raw, "pictures") and raw.pictures:
            pic = raw.pictures[0]
            return pic.data, (pic.mime or "image/jpeg")
        tags = raw.tags
        if tags is None:
            return None, None
        if hasattr(tags, "getall"):
            apic = tags.getall("APIC")
            if apic:
                return apic[0].data, (apic[0].mime or "image/jpeg")
        if raw.__class__.__name__ in ("MP4", "M4A", "AAC"):
            cov = tags.get("covr")
            if cov:
                c = cov[0]
                fmt = "image/png" if getattr(c, "imageformat", 13) == 14 else "image/jpeg"
                return bytes(c), fmt
    except Exception:
        pass
    return None, None

# ============================================================================
# §6  USB FILING & CRATES  (send to USB, reconcile membership, crate tree)
# ============================================================================
def get_active_usb(lib):
    aid = lib.get("active_usb")
    for u in lib.get("usbs", []):
        if u["id"] == aid:
            return u
    return None

def _within_any_usb(path, lib):
    ap = os.path.abspath(path)
    for u in lib.get("usbs", []):
        if ap.startswith(os.path.abspath(u["path"]) + os.sep):
            return u
    return None

def _unique(dest):
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest); n = 2
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"

def _rmdir_if_empty(d, lib):
    if _within_any_usb(d + os.sep, lib):
        try:
            if not os.listdir(d):
                os.rmdir(d)
        except Exception:
            pass

def file_into_usb(track, lib):
    """File a track into <active USB>/<genre>/ using the chosen mode (copy/move).
    Returns a dict describing what happened (for undo + UI), or None."""
    usb = get_active_usb(lib)
    genre = (track.get("genre") or "").strip()
    if not usb or not genre:
        return None
    cur = track["path"]
    if not os.path.isfile(cur):
        return None
    mode = lib.get("usb_mode", "copy")
    target_dir = os.path.join(usb["path"], safe_name(genre))
    os.makedirs(target_dir, exist_ok=True)
    dest = os.path.join(target_dir, os.path.basename(cur))

    if mode == "move":
        if os.path.abspath(cur) == os.path.abspath(dest):
            track["usb"] = usb["id"]; track["usb_genre"] = genre
            return None
        dest = _unique(dest)
        shutil.move(cur, dest)
        old_parent = os.path.dirname(cur)
        track["path"] = dest; track["usb"] = usb["id"]; track["usb_genre"] = genre
        _rmdir_if_empty(old_parent, lib)
        return {"mode": "move", "old": cur, "new": dest, "usb": usb["name"], "genre": genre}

    # ---- copy mode (default): the original never leaves the source ----
    prev_usb, prev_g = track.get("usb"), track.get("usb_genre")
    if prev_usb == usb["id"] and prev_g and prev_g != genre:
        # genre changed: relocate the existing USB copy instead of duplicating it
        oldc = os.path.join(usb["path"], safe_name(prev_g), os.path.basename(cur))
        if os.path.isfile(oldc):
            dest = _unique(dest)
            shutil.move(oldc, dest)
            _rmdir_if_empty(os.path.dirname(oldc), lib)
            track["usb"] = usb["id"]; track["usb_genre"] = genre
            return {"mode": "move", "old": oldc, "new": dest, "usb": usb["name"], "genre": genre}
    if os.path.exists(dest):
        track["usb"] = usb["id"]; track["usb_genre"] = genre
        return {"mode": "copy", "created": False, "new": dest, "usb": usb["name"], "genre": genre}
    shutil.copy2(cur, dest)
    track["usb"] = usb["id"]; track["usb_genre"] = genre
    return {"mode": "copy", "created": True, "old": cur, "new": dest, "usb": usb["name"], "genre": genre}

def usb_membership(path, lib):
    """If the file physically lives inside a registered USB, return (usb_id, genre_subfolder)."""
    u = _within_any_usb(path, lib)
    if not u:
        return "", ""
    rel = os.path.relpath(path, u["path"])
    parts = rel.split(os.sep)
    return u["id"], (parts[0] if len(parts) >= 2 else "")

def _refile_track_usb(track, lib, new_genre):
    """Move a track's USB file/copy from its old genre folder to the new one."""
    uid = track.get("usb")
    usb = next((u for u in lib.get("usbs", []) if u["id"] == uid), None)
    if not usb:
        return None
    old_g = track.get("usb_genre") or ""
    if old_g == new_genre:
        return None
    in_usb = os.path.abspath(track["path"]).startswith(os.path.abspath(usb["path"]) + os.sep)
    cur = track["path"] if in_usb else os.path.join(usb["path"], safe_name(old_g), os.path.basename(track["path"]))
    if not os.path.isfile(cur):
        track["usb_genre"] = new_genre
        return None
    dest = _unique(os.path.join(usb["path"], safe_name(new_genre), os.path.basename(cur)))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(cur, dest)
    _rmdir_if_empty(os.path.dirname(cur), lib)
    if in_usb:
        track["path"] = dest
    track["usb_genre"] = new_genre
    return {"old": cur, "new": dest}

def _crate_node(path, depth=0):
    node = {"name": os.path.basename(path.rstrip(os.sep)) or path, "path": path, "subs": []}
    if depth < 3 and os.path.isdir(path):
        try:
            for n in sorted(os.listdir(path)):
                p = os.path.join(path, n)
                if os.path.isdir(p) and not n.startswith("."):
                    node["subs"].append(_crate_node(p, depth + 1))
        except Exception:
            pass
    return node

def crates_payload(lib):
    out = []
    for c in lib.get("crates", []):
        if os.path.isdir(c["path"]):
            node = _crate_node(c["path"]); node["id"] = c["id"]; node["name"] = c["name"]
            out.append(node)
    return out

# ============================================================================
# §7  SCANNING & TRACK BUILDING  (walk folders, build/refresh track records)
# ============================================================================
def _build_track(path, lib, source=None):
    finfo = read_file_tags(path)
    notes_f, struct_f = _parse_comment(finfo.get("comment", ""))
    existing = lib["tracks"].get(path, {})
    base = os.path.splitext(os.path.basename(path))[0]
    usb_id, usb_g = usb_membership(path, lib)   # analyze where the file actually is
    if not usb_id:                              # not physically in a USB; keep any prior "copied-to" marker
        usb_id = existing.get("usb", ""); usb_g = existing.get("usb_genre", "")
    return {
        "path": path, "filename": os.path.basename(path),
        "artist": existing.get("artist") or finfo["artist"], "title": base,
        "bpm": finfo["bpm"] or existing.get("bpm", ""), "key": finfo["key"] or existing.get("key", ""),
        "bitrate": finfo.get("bitrate", 0), "lossless": finfo.get("lossless", False),
        "genre": existing.get("genre") if existing.get("genre") is not None else (finfo["genre"] or ""),
        "energy": existing.get("energy", _to_int(struct_f.get("energy"))),
        "rating": existing.get("rating", _to_int(struct_f.get("rating"))),
        "tags": existing.get("tags", _split_tags(struct_f.get("tags"))),
        "notes": existing.get("notes", notes_f),
        "custom": existing.get("custom", _recover_custom(struct_f, lib["fields"])),
        "source": source if source else existing.get("source", ""),
        "hidden": existing.get("hidden", False),
        "usb": usb_id, "usb_genre": usb_g,
    }

def scan_folder(folder, lib, source=None):
    source = source or folder
    found = []
    for root, _d, files in os.walk(folder):
        for name in files:
            if not name.startswith(".") and name.lower().endswith(AUDIO_EXTS):
                found.append(os.path.join(root, name))
    # Heal any WAV/AIFF a prior version corrupted (leading ID3 tag) so they read/play
    # correctly again. Cheap: only reads 10 bytes unless a file is actually damaged.
    for p in found:
        if os.path.splitext(p)[1].lower() in (".wav", ".aiff", ".aif"):
            _repair_container(p)
    seen = set(found)
    # Reading tags (mutagen) is I/O-bound: overlap the reads across a small thread pool.
    # _build_track only READS lib here, so concurrent reads are safe; results are assigned
    # sequentially afterward, giving byte-for-byte the same library as the serial version.
    if len(found) > 4:
        with ThreadPoolExecutor(max_workers=min(8, (os.cpu_count() or 4) * 2)) as ex:
            built = list(ex.map(lambda p: (p, _build_track(p, lib, source)), found))
        for path, tr in built:
            lib["tracks"][path] = tr
    else:
        for path in found:
            lib["tracks"][path] = _build_track(path, lib, source)
    for path in list(lib["tracks"].keys()):
        if path in seen:
            continue
        if not os.path.isfile(path):
            del lib["tracks"][path]
    return all_tracks(lib)

def reconcile_usb(lib):
    """Recheck every USB folder on disk and mark/unmark library tracks accordingly.
    A track is considered 'on a USB' if a file with the same name exists somewhere
    under that USB's folder; its usb_genre becomes the sub-folder it sits in.
    Markers are only cleared for USBs that are currently mounted (so unplugging a
    drive doesn't wipe membership)."""
    usbs = lib.get("usbs", [])
    available = set()
    on_disk = {}   # basename -> (usb_id, genre)
    for usb in usbs:
        base = usb.get("path", "")
        if not base or not os.path.isdir(base):
            continue
        available.add(usb["id"])
        base_abs = os.path.abspath(base)               # hoisted out of the walk loop
        for root, _d, files in os.walk(base):
            genre = "" if os.path.abspath(root) == base_abs else os.path.basename(root)
            for fn in files:
                if not fn.startswith(".") and fn.lower().endswith(AUDIO_EXTS):
                    on_disk.setdefault(fn, (usb["id"], genre))
    changed = 0
    for p, tr in lib["tracks"].items():
        bn = os.path.basename(tr.get("path", p))
        hit = on_disk.get(bn)
        if hit:
            new_usb, new_g = hit[0], (hit[1] or tr.get("genre", ""))
            if tr.get("usb") != new_usb or tr.get("usb_genre") != new_g:
                tr["usb"], tr["usb_genre"] = new_usb, new_g; changed += 1
        elif tr.get("usb") in available:
            # the drive is mounted but the file isn't there anymore -> stale marker
            tr["usb"], tr["usb_genre"] = "", ""; changed += 1
    return changed

def all_tracks(lib):
    tracks = lib["tracks"]
    out, missing = [], []
    for path, tr in tracks.items():        # single pass; no second dict lookup per row
        if os.path.isfile(path):
            out.append(tr)
        else:
            missing.append(path)
    for path in missing:
        del tracks[path]
    out.sort(key=lambda t: (t.get("title") or t.get("filename") or "").lower())
    return out

# ============================================================================
# §8  CUSTOM FIELDS  (user-defined columns <-> values embedded in the comment)
# ============================================================================
def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

def _split_tags(v):
    return [t.strip() for t in str(v).split(",") if t.strip()] if v else []

def _recover_custom(struct, fields):
    out = {}
    for fdef in fields:
        key = "cf_" + fdef["name"]
        if key in struct:
            out[fdef["name"]] = struct[key]
    return out

def struct_for_track(track, fields):
    struct = {}
    if track.get("energy"):
        struct["energy"] = track["energy"]
    if track.get("rating"):
        struct["rating"] = track["rating"]
    if track.get("tags"):
        struct["tags"] = track["tags"]
    for fdef in fields:
        val = (track.get("custom") or {}).get(fdef["name"])
        if val not in (None, "", []):
            struct["cf_" + fdef["name"]] = val
    return struct

# ============================================================================
# §9  NATIVE DIALOGS & EXPORT  (macOS folder pickers, text prompts, flat export)
# ============================================================================
def _asc(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')

def choose_folder(prompt, default=None):
    if sys.platform != "darwin":
        return ""
    s = "try\n"
    if default and os.path.isdir(default):
        s += f'set f to choose folder with prompt "{_asc(prompt)}" default location (POSIX file "{_asc(default)}")\n'
    else:
        s += f'set f to choose folder with prompt "{_asc(prompt)}"\n'
    s += "POSIX path of f\nend try"
    try:
        return subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=300).stdout.strip()
    except Exception:
        return ""

def prompt_text(prompt, default_answer=""):
    if sys.platform != "darwin":
        return ""
    s = (f'try\nset r to text returned of (display dialog "{_asc(prompt)}" default answer '
         f'"{_asc(default_answer)}" with title "DJ Music Library")\nr\nend try')
    try:
        return subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=300).stdout.strip()
    except Exception:
        return ""

def export_tracks(paths, dest_parent, folder_name):
    dest_parent = dest_parent or os.path.expanduser("~/Music")
    target = os.path.join(dest_parent, safe_name(folder_name or "DJ Set"))
    os.makedirs(target, exist_ok=True)
    copied, errors = 0, []
    for p in paths:
        if not os.path.isfile(p):
            errors.append(f"missing: {p}"); continue
        try:
            dest = os.path.join(target, os.path.basename(p))
            if os.path.exists(dest):
                base, ext = os.path.splitext(dest); n = 2
                while os.path.exists(f"{base} ({n}){ext}"):
                    n += 1
                dest = f"{base} ({n}){ext}"
            shutil.copy2(p, dest); copied += 1
        except Exception as e:
            errors.append(f"{os.path.basename(p)}: {e}")
    return {"copied": copied, "target": target, "errors": errors}

# ============================================================================
# §10  HTTP SERVER & API ROUTES
#   The Handler dispatches POST /api/<name> to a method named _route_api_<name>
#   (see do_POST). To add an endpoint, add one _route_api_<name>(self) method.
# ============================================================================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                body = f.read()
        except Exception:
            self.send_error(404); return
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

    def _serve_bytes(self, data, ctype):
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_audio(self, path):
        if not path or not os.path.isfile(path):
            self.send_error(404); return
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        start, end, partial = 0, size - 1, False
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                end = min(end, size - 1)
                if start > end:
                    start = 0
                partial = True
        length = end - start + 1
        try:
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", ctype); self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(path, "rb") as f:
                f.seek(start); remaining = length
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk); remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html", "/app.html"):
            self._file(APP_HTML_PATH, "text/html; charset=utf-8")
        elif parsed.path == "/audio":
            qs = urllib.parse.parse_qs(parsed.query)
            self._serve_audio(qs.get("path", [""])[0])
        elif parsed.path == "/cover":
            qs = urllib.parse.parse_qs(parsed.query)
            data, mime = get_cover(qs.get("path", [""])[0])
            if data:
                self._serve_bytes(data, mime or "image/jpeg")
            else:
                self.send_error(404)
        elif parsed.path == "/logo":
            lp = os.path.join(resource_dir(), "logo.png")
            if os.path.exists(lp):
                self._file(lp, "image/png")
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        try:
            route = getattr(self, "_route_" + self.path.strip("/").replace("/", "_"), None)
            if route is None:
                self.send_error(404); return
            route()
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _state_payload(self, lib):
        return {"folder": lib["folder"], "sources": lib.get("sources", []),
                "fields": lib["fields"], "usbs": lib["usbs"],
                "active_usb": lib["active_usb"], "auto_file": lib.get("auto_file", False),
                "usb_mode": lib.get("usb_mode", "copy"),
                "crate_base": lib.get("crate_base", ""), "crates": crates_payload(lib),
                "welcomed": lib.get("welcomed", False),
                "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0, "tracks": all_tracks(lib)}

    def _route_api_state(self):
        with LIB_LOCK:
            lib = load_library(); payload = self._state_payload(lib); save_library(lib)
        self._json(payload)

    def _route_api_set_welcomed(self):
        with LIB_LOCK:
            lib = load_library(); lib["welcomed"] = True; save_library(lib)
        self._json({"ok": True})

    def _route_api_pick_folder(self):
        with LIB_LOCK:
            lib = load_library()
        self._json({"folder": choose_folder("Select your music folder:", lib.get("folder"))})

    def _route_api_scan(self):
        data = self._body(); folder = data.get("folder", "").strip()
        if not folder or not os.path.isdir(folder):
            self._json({"error": "Folder not found."}, 400); return
        with LIB_LOCK:
            lib = load_library(); lib["folder"] = folder
            if folder not in lib.get("sources", []):
                lib.setdefault("sources", []).append(folder)
            scan_folder(folder, lib, folder)
            reconcile_usb(lib)                       # detect songs already sitting on a USB
            active = get_active_usb(lib)
            dups = 0
            if active:
                for p, tr in lib["tracks"].items():
                    if tr.get("source") == folder and tr.get("usb") == active["id"]:
                        dups += 1
            save_library(lib); payload = self._state_payload(lib)
            payload["added"] = folder
            payload["usb_dups"] = dups
            payload["usb_name"] = active["name"] if active else ""
        self._json(payload)

    def _route_api_rescan_all(self):
        with LIB_LOCK:
            lib = load_library()
            for f in list(lib.get("sources", [])):
                if os.path.isdir(f):
                    scan_folder(f, lib, f)
            reconcile_usb(lib)
            save_library(lib); payload = self._state_payload(lib)
        self._json(payload)

    def _route_api_remove_source(self):
        data = self._body(); folder = data.get("folder", "")
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            lib["sources"] = [s for s in lib.get("sources", []) if s != folder]
            for p in list(lib["tracks"].keys()):
                if lib["tracks"][p].get("source") == folder:
                    del lib["tracks"][p]
            push_undo(snap, [], [], "remove folder", after=lib)
            save_library(lib); payload = self._state_payload(lib)
        self._json(payload)

    def _route_api_remove_sources(self):
        data = self._body(); folders = set(data.get("folders") or [])
        if not folders:
            self._json({"error": "No folders given."}, 400); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            lib["sources"] = [s for s in lib.get("sources", []) if s not in folders]
            for p in list(lib["tracks"].keys()):
                if lib["tracks"][p].get("source") in folders:
                    del lib["tracks"][p]
            push_undo(snap, [], [], f"remove {len(folders)} folders", after=lib)
            save_library(lib); payload = self._state_payload(lib)
        self._json(payload)

    def _route_api_save_track(self):
        data = self._body()
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            path = data["path"]; tr = lib["tracks"].get(path, {"path": path})
            for k in ("genre", "energy", "rating", "tags", "notes", "custom", "artist", "title", "bpm", "key", "filename", "hidden"):
                if k in data:
                    tr[k] = data[k]
            struct = struct_for_track(tr, lib["fields"])
            ok, msg = write_file_tags(tr["path"], genre=tr.get("genre", ""), notes=tr.get("notes", ""),
                                      struct=struct, artist=tr.get("artist", ""), title=tr.get("title", ""))
            moves, copies, moved = [], [], None
            rename_to = (data.get("rename_to") or "").strip()
            if rename_to:
                cur = tr["path"]; ext = os.path.splitext(cur)[1]
                newp = os.path.join(os.path.dirname(cur), safe_name(rename_to) + ext)
                if os.path.abspath(newp) != os.path.abspath(cur) and os.path.isfile(cur):
                    if os.path.exists(newp):
                        b, e = os.path.splitext(newp); n = 2
                        while os.path.exists(f"{b} ({n}){e}"):
                            n += 1
                        newp = f"{b} ({n}){e}"
                    try:
                        os.rename(cur, newp); moves.append([newp, cur])
                        tr["path"] = newp; tr["filename"] = os.path.basename(newp)
                        tr["title"] = os.path.splitext(tr["filename"])[0]
                    except Exception:
                        pass
            active = get_active_usb(lib); auto = lib.get("auto_file", False)
            if auto and (tr.get("genre") or "").strip() and active:
                moved = file_into_usb(tr, lib)
                if moved and moved["mode"] == "move":
                    moves.append([moved["new"], moved["old"]])
                elif moved and moved["mode"] == "copy" and moved.get("created"):
                    copies.append([moved.get("old"), moved["new"]])
            if tr["path"] != path:
                lib["tracks"].pop(path, None)
            lib["tracks"][tr["path"]] = tr
            push_undo(snap, moves, [path], "edit " + os.path.basename(path), copies, after=lib)
            save_library(lib)
            no_usb = bool(auto and (tr.get("genre") or "").strip() and not active)
        self._json({"ok": ok, "embed": msg, "track": tr, "moved": moved, "no_usb": no_usb, "can_undo": True})

    def _route_api_delete_genre(self):
        data = self._body(); genre = (data.get("genre") or "").strip()
        if not genre:
            self._json({"error": "No genre given."}, 400); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib); touched = []
            for p, tr in lib["tracks"].items():
                if (tr.get("genre") or "").strip() == genre:
                    tr["genre"] = ""
                    if os.path.isfile(p):
                        write_file_tags(p, genre="", notes=tr.get("notes", ""),
                                        struct=struct_for_track(tr, lib["fields"]),
                                        artist=tr.get("artist", ""), title=tr.get("title", ""))
                    touched.append(p)
            push_undo(snap, [], touched, "delete genre " + genre, after=lib)
            save_library(lib); payload = self._state_payload(lib); payload["cleared"] = len(touched)
        self._json(payload)

    def _route_api_delete_genres(self):
        data = self._body()
        genres = set((g or "").strip() for g in (data.get("genres") or []) if (g or "").strip())
        if not genres:
            self._json({"error": "No genres given."}, 400); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib); touched = []
            for p, tr in lib["tracks"].items():
                if (tr.get("genre") or "").strip() in genres:
                    tr["genre"] = ""
                    if os.path.isfile(p):
                        write_file_tags(p, genre="", notes=tr.get("notes", ""),
                                        struct=struct_for_track(tr, lib["fields"]),
                                        artist=tr.get("artist", ""), title=tr.get("title", ""))
                    touched.append(p)
            push_undo(snap, [], touched, f"delete {len(genres)} genres", after=lib)
            save_library(lib); payload = self._state_payload(lib); payload["cleared"] = len(touched)
        self._json(payload)

    def _route_api_set_auto_file(self):
        data = self._body()
        with LIB_LOCK:
            lib = load_library(); lib["auto_file"] = bool(data.get("on")); save_library(lib); val = lib["auto_file"]
        self._json({"auto_file": val, "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0})

    def _route_api_set_usb_mode(self):
        data = self._body(); mode = "move" if data.get("mode") == "move" else "copy"
        with LIB_LOCK:
            lib = load_library(); lib["usb_mode"] = mode; save_library(lib)
        self._json({"usb_mode": mode})

    def _route_api_genre_plan(self):
        with LIB_LOCK:
            lib = load_library()
            counts = {}
            for tr in lib["tracks"].values():
                g = (tr.get("genre") or "").strip()
                if g:
                    counts[g] = counts.get(g, 0) + 1
            groups = {}
            for g, c in counts.items():
                groups.setdefault(_norm_genre(g), {})[g] = c
            auto, review = [], []
            for k, members in groups.items():
                to = _canonical_display(k, members)
                spellings = list(members.keys())
                if len(spellings) == 1 and spellings[0] == to:
                    continue                                  # already clean
                if len(spellings) == 1 and ("/" in spellings[0] or "," in spellings[0]):
                    continue                                  # leave compound tags alone
                mlist = [{"genre": g, "count": c} for g, c in sorted(members.items(), key=lambda x: -x[1])]
                entry = {"to": to, "members": mlist}
                # case-only change (e.g. WORLD->World, HOUSE->House) => needs your OK, NOT auto
                case_only = (set(s.lower() for s in spellings) == {to.lower()})
                (review if case_only else auto).append(entry)
            # fuzzy near-duplicate normalized keys (typo-level), conservative => review
            seen = set()
            keys = list(groups.keys())
            for i in range(len(keys)):
                for j in range(i + 1, len(keys)):
                    a, b = keys[i], keys[j]
                    if a in seen or b in seen or min(len(a), len(b)) < 4:
                        continue
                    if _lev(a, b) == 1:
                        merged = dict(groups[a]); merged.update(groups[b])
                        ck = a if a in CANONICAL_DISPLAY else (b if b in CANONICAL_DISPLAY else a)
                        review.append({"to": _canonical_display(ck, merged),
                                       "members": [{"genre": g, "count": c} for g, c in
                                                   sorted(merged.items(), key=lambda x: -x[1])]})
                        seen.add(a); seen.add(b)
        self._json({"auto": auto, "review": review})

    def _route_api_genre_apply(self):
        data = self._body()
        merges = data.get("merges", [])
        refile = bool(data.get("refile"))
        mapping = {}
        for grp in merges:
            to = (grp.get("to") or "").strip()
            if not to:
                continue
            for orig in grp.get("members", []):
                if orig != to:
                    mapping[orig] = to
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            touched, moves, changed = [], [], 0
            for p, tr in list(lib["tracks"].items()):
                g = (tr.get("genre") or "")
                if g in mapping:
                    newg = mapping[g]
                    tr["genre"] = newg
                    if os.path.isfile(p):
                        write_file_tags(p, genre=newg, notes=tr.get("notes", ""),
                                        struct=struct_for_track(tr, lib["fields"]),
                                        artist=tr.get("artist", ""), title=tr.get("title", ""))
                    touched.append(p)
                    changed += 1
                    if refile and tr.get("usb"):
                        mv = _refile_track_usb(tr, lib, newg)
                        if mv:
                            moves.append([mv["new"], mv["old"]])
                            if tr["path"] != p:
                                lib["tracks"].pop(p, None); lib["tracks"][tr["path"]] = tr
            push_undo(snap, moves, touched, f"merge genres ({changed})", after=lib)
            save_library(lib)
            payload = self._state_payload(lib); payload["merged"] = changed
        self._json(payload)

    def _route_api_add_crate(self):
        data = self._body(); name = (data.get("name") or "").strip()
        use_existing = bool(data.get("use_existing"))
        if not name and not use_existing:
            self._json({"error": "Crate needs a name."}, 400); return
        lib0 = load_library()
        if use_existing:
            chosen = data.get("parent") or choose_folder("Choose a folder to use as a crate:")
            if not chosen:
                self._json({"cancelled": True}); return
            path = chosen; name = name or os.path.basename(chosen.rstrip(os.sep))
        else:
            base = data.get("parent") or lib0.get("crate_base", "")
            if not base:
                base = choose_folder("Choose a base folder to keep your crates in:")
            if not base:
                self._json({"cancelled": True}); return
            path = os.path.join(base, safe_name(name))
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                self._json({"error": str(e)}, 500); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            if not use_existing and not lib.get("crate_base"):
                lib["crate_base"] = os.path.dirname(path)
            if not any(c["path"] == path for c in lib.get("crates", [])):
                lib.setdefault("crates", []).append({"id": uuid.uuid4().hex[:8], "name": name, "path": path})
            push_undo(snap, [], [], "add crate", after=lib, dirs=([path] if not use_existing else []))
            save_library(lib)
            payload = {"crates": crates_payload(lib), "crate_base": lib.get("crate_base", ""),
                       "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0}
        self._json(payload)

    def _route_api_add_subcrate(self):
        data = self._body(); parent = data.get("parent", ""); name = (data.get("name") or "").strip()
        if not parent or not os.path.isdir(parent) or not name:
            self._json({"error": "Pick a name for the sub-folder."}, 400); return
        newdir = os.path.join(parent, safe_name(name))
        existed = os.path.isdir(newdir)
        try:
            os.makedirs(newdir, exist_ok=True)
        except Exception as e:
            self._json({"error": str(e)}, 500); return
        with LIB_LOCK:
            lib = load_library()
            push_undo(copy.deepcopy(lib), [], [], "add sub-folder", after=lib,
                      dirs=([newdir] if not existed else []))
            payload = {"crates": crates_payload(lib), "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0}
        self._json(payload)

    def _route_api_remove_crate(self):
        data = self._body(); cid = data.get("id")
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            lib["crates"] = [c for c in lib.get("crates", []) if c["id"] != cid]
            push_undo(snap, [], [], "remove crate", after=lib)
            save_library(lib)
            payload = {"crates": crates_payload(lib), "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0}
        self._json(payload)

    def _route_api_crate_drop(self):
        data = self._body(); paths = data.get("paths", []); dest = data.get("dest", "")
        if not dest or not os.path.isdir(dest):
            self._json({"error": "Crate folder not found."}, 400); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib); mode = lib.get("usb_mode", "copy")
            moves, copies, count = [], [], 0
            for p in paths:
                if not os.path.isfile(p):
                    continue
                d = _unique(os.path.join(dest, os.path.basename(p)))
                try:
                    if mode == "move":
                        shutil.move(p, d); moves.append([d, p]); count += 1
                        tr = lib["tracks"].pop(p, None)
                        if tr:
                            tr["path"] = d; tr["filename"] = os.path.basename(d); lib["tracks"][d] = tr
                    else:
                        shutil.copy2(p, d); copies.append([p, d]); count += 1
                except Exception:
                    pass
            reconcile_usb(lib)   # if the crate lives on a USB, show the badge immediately
            if moves or copies:
                push_undo(snap, moves, [], f"drop {count} into crate", copies, after=lib)
            save_library(lib); payload = self._state_payload(lib); payload["dropped"] = count; payload["mode"] = mode
        self._json(payload)

    def _route_api_reveal(self):
        data = self._body(); p = data.get("path", "")
        if p and os.path.exists(p) and sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-R", p])
            except Exception:
                pass
        self._json({"ok": True})

    def _route_api_send_to_usb(self):
        data = self._body(); paths = data.get("paths", [])
        with LIB_LOCK:
            lib = load_library(); active = get_active_usb(lib)
            if not active:
                self._json({"error": "No active USB. Create or select one first."}, 400); return
            snap = copy.deepcopy(lib); results, skipped, moves, copies = [], [], [], []
            for path in paths:
                tr = lib["tracks"].get(path)
                if not tr:
                    skipped.append({"path": path, "reason": "not in library"}); continue
                if not (tr.get("genre") or "").strip():
                    skipped.append({"path": path, "reason": "no genre set"}); continue
                old = tr["path"]; moved = file_into_usb(tr, lib)
                if tr["path"] != old:
                    lib["tracks"].pop(old, None); lib["tracks"][tr["path"]] = tr
                if moved and moved["mode"] == "move":
                    moves.append([moved["new"], moved["old"]])
                elif moved and moved["mode"] == "copy" and moved.get("created"):
                    copies.append([moved.get("old"), moved["new"]])
                results.append({"old": old, "track": tr, "moved": moved})
            if moves or copies:
                push_undo(snap, moves, [], f"send {len(moves)+len(copies)} to {active['name']}", copies, after=lib)
            save_library(lib); usb_name = active["name"]
        self._json({"results": results, "skipped": skipped, "usb": usb_name, "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0})

    def _route_api_add_field(self):
        data = self._body(); name = (data.get("name") or "").strip()
        if not name:
            self._json({"error": "Field needs a name."}, 400); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            if not any(f["name"] == name for f in lib["fields"]):
                lib["fields"].append({"name": name, "type": data.get("type", "text")})
                push_undo(snap, [], [], "add field " + name, after=lib)
            save_library(lib); fields = lib["fields"]
        self._json({"fields": fields, "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0})

    def _route_api_remove_field(self):
        data = self._body(); name = data.get("name")
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            lib["fields"] = [f for f in lib["fields"] if f["name"] != name]
            for tr in lib["tracks"].values():
                if "custom" in tr and name in tr["custom"]:
                    del tr["custom"][name]
            push_undo(snap, [], [], "remove field " + str(name), after=lib)
            save_library(lib); fields = lib["fields"]
        self._json({"fields": fields, "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0})

    def _route_api_add_usb(self):
        data = self._body(); name = (data.get("name") or "").strip()
        if not name:
            self._json({"error": "USB needs a name."}, 400); return
        use_existing = bool(data.get("use_existing")); chosen = data.get("parent")
        if not chosen:
            prompt = ("Choose the existing folder to use as this USB:" if use_existing
                      else "Choose where to create the USB folder for: " + name)
            chosen = choose_folder(prompt)
        if not chosen:
            self._json({"cancelled": True}); return
        path = chosen if use_existing else os.path.join(chosen, safe_name(name))
        if not use_existing:
            os.makedirs(path, exist_ok=True)
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            usb = {"id": uuid.uuid4().hex[:8], "name": name, "path": path}
            lib["usbs"].append(usb)
            if not lib["active_usb"]:
                lib["active_usb"] = usb["id"]
            push_undo(snap, [], [], "add USB " + name, after=lib)
            save_library(lib)
            payload = {"usbs": lib["usbs"], "active_usb": lib["active_usb"], "created": usb, "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0}
        self._json(payload)

    def _route_api_set_active_usb(self):
        data = self._body()
        with LIB_LOCK:
            lib = load_library(); lib["active_usb"] = data.get("id", ""); save_library(lib)
            payload = {"usbs": lib["usbs"], "active_usb": lib["active_usb"], "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0}
        self._json(payload)

    def _route_api_remove_usb(self):
        data = self._body(); uid = data.get("id")
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib)
            lib["usbs"] = [u for u in lib["usbs"] if u["id"] != uid]
            if lib["active_usb"] == uid:
                lib["active_usb"] = lib["usbs"][0]["id"] if lib["usbs"] else ""
            push_undo(snap, [], [], "remove USB", after=lib)
            save_library(lib)
            payload = {"usbs": lib["usbs"], "active_usb": lib["active_usb"], "can_undo": len(UNDO) > 0, "can_redo": len(REDO) > 0}
        self._json(payload)

    def _reembed(self, lib, paths):
        for p in paths:
            tr = lib["tracks"].get(p)
            if tr and os.path.isfile(p):
                write_file_tags(p, genre=tr.get("genre", ""), notes=tr.get("notes", ""),
                                struct=struct_for_track(tr, lib["fields"]),
                                artist=tr.get("artist", ""), title=tr.get("title", ""))

    def _route_api_undo(self):
        with LIB_LOCK:
            if not UNDO:
                self._json({"error": "Nothing to undo."}, 400); return
            e = UNDO.pop()
            for src, dst in _norm_copies(e.get("copies")):   # created copies -> delete
                try:
                    if os.path.isfile(dst):
                        os.remove(dst); _rmdir_if_empty(os.path.dirname(dst), e["before"])
                except Exception:
                    pass
            for new, old in reversed(e.get("moves", [])):     # move back new -> old
                try:
                    if os.path.isfile(new):
                        os.makedirs(os.path.dirname(old), exist_ok=True); shutil.move(new, old)
                except Exception:
                    pass
            for d in reversed(e.get("dirs", [])):              # remove created dirs (if empty)
                try:
                    if os.path.isdir(d) and not os.listdir(d):
                        os.rmdir(d)
                except Exception:
                    pass
            lib = copy.deepcopy(e["before"])   # copy so the canonical lib never aliases history
            self._reembed(lib, e.get("touched", []))
            save_library(lib); REDO.append(e)
            payload = self._state_payload(lib); payload["undone"] = e["label"]
        self._json(payload)

    def _route_api_redo(self):
        with LIB_LOCK:
            if not REDO:
                self._json({"error": "Nothing to redo."}, 400); return
            e = REDO.pop()
            for d in e.get("dirs", []):                        # recreate dirs
                try:
                    os.makedirs(d, exist_ok=True)
                except Exception:
                    pass
            for new, old in e.get("moves", []):                # redo move old -> new
                try:
                    if os.path.isfile(old):
                        os.makedirs(os.path.dirname(new), exist_ok=True); shutil.move(old, new)
                except Exception:
                    pass
            for src, dst in _norm_copies(e.get("copies")):     # redo copy src -> dst
                try:
                    if src and os.path.isfile(src) and not os.path.exists(dst):
                        os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(src, dst)
                except Exception:
                    pass
            lib = copy.deepcopy(e["after"] if e.get("after") is not None else e["before"])
            self._reembed(lib, e.get("touched", []))
            save_library(lib); UNDO.append(e)
            payload = self._state_payload(lib); payload["redone"] = e["label"]
        self._json(payload)

    def _route_api_export(self):
        data = self._body(); paths = data.get("paths", [])
        if not paths:
            self._json({"error": "No tracks selected."}, 400); return
        parent = data.get("dest_parent"); name = data.get("folder_name")
        if not parent:
            parent = choose_folder("Choose where to create the set folder:")
            if not parent:
                self._json({"cancelled": True}); return
        if not name:
            name = prompt_text("Name this set folder:", "My Set")
            if not name:
                self._json({"cancelled": True}); return
        self._json(export_tracks(paths, parent, name))

    def _route_api_export_folders(self):
        """Copy every track from one or more folders into a single flat folder,
        ready to drop into Serato / rekordbox."""
        data = self._body(); folders = set(data.get("folders") or [])
        if not folders:
            self._json({"error": "No folders given."}, 400); return
        with LIB_LOCK:
            lib = load_library()
            paths = []
            for p, tr in lib["tracks"].items():
                src = tr.get("source")
                if src in folders or any(p.startswith(f.rstrip(os.sep) + os.sep) for f in folders):
                    if os.path.isfile(p):
                        paths.append(p)
        if not paths:
            self._json({"error": "No tracks found in those folders."}, 400); return
        parent = data.get("dest_parent")
        if not parent:
            parent = choose_folder("Choose where to create the export folder:")
            if not parent:
                self._json({"cancelled": True}); return
        name = data.get("folder_name")
        if not name:
            name = prompt_text("Name this export folder:", "ONDA Export")
            if not name:
                self._json({"cancelled": True}); return
        self._json(export_tracks(paths, parent, name))

    def _route_api_set_genre_bulk(self):
        """Set the same genre on many tracks at once (one undo step)."""
        data = self._body()
        paths = data.get("paths", []); genre = (data.get("genre") or "").strip()
        if not paths:
            self._json({"error": "No tracks selected."}, 400); return
        with LIB_LOCK:
            lib = load_library(); snap = copy.deepcopy(lib); touched = []
            for p in paths:
                tr = lib["tracks"].get(p)
                if not tr:
                    continue
                tr["genre"] = genre
                if os.path.isfile(p):
                    write_file_tags(p, genre=genre, notes=tr.get("notes", ""),
                                    struct=struct_for_track(tr, lib["fields"]),
                                    artist=tr.get("artist", ""), title=tr.get("title", ""))
                touched.append(p)
            push_undo(snap, [], touched, f"set genre on {len(touched)}", after=lib)
            save_library(lib); payload = self._state_payload(lib); payload["changed"] = len(touched)
        self._json(payload)


# ============================================================================
# §11  SERVER BOOTSTRAP / main()  (pick a port, open native window, run)
# ============================================================================
def find_free_port(preferred=8765):
    for port in [preferred] + list(range(8766, 8810)):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def _idle(server):
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        flush_library(); server.shutdown()

APP_WINDOW_BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

def main():
    _require_mutagen()
    atexit.register(flush_library)   # never lose pending write-behind changes on exit
    if not os.path.exists(APP_HTML_PATH):
        print("ERROR: app.html is missing. Keep music_library.py and app.html together.")
        sys.exit(1)
    import tempfile
    port = find_free_port()
    url = f"http://127.0.0.1:{port}/"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("ONDA is running at", url)
    mode = os.environ.get("DJLIB_UI", "auto").lower()

    # 1) True native window, if pywebview is installed
    if mode in ("auto", "webview"):
        try:
            import webview
            webview.create_window("ONDA", url,
                                  width=1240, height=800, min_size=(940, 620))
            webview.start()           # blocks until the window is closed
            server.shutdown(); return
        except Exception as e:
            print("Native window unavailable:", e, "- trying an app window...")

    # 2) Separate app-mode window in a Chromium browser (no tabs / no address bar)
    if mode in ("auto", "chrome"):
        for app_bin in APP_WINDOW_BROWSERS:
            if os.path.exists(app_bin):
                prof = os.path.join(tempfile.gettempdir(), "djlib-appwin")
                try:
                    subprocess.Popen([app_bin, f"--app={url}",
                                      f"--user-data-dir={prof}",
                                      "--window-size=1240,820", "--no-first-run",
                                      "--no-default-browser-check"])
                    print("Opened a separate app window. Close this window (or Ctrl+C) to quit.")
                    _idle(server); return
                except Exception:
                    pass

    # 3) Fallback: default browser tab
    webbrowser.open(url)
    print("Opened in your browser. Close this window (or Ctrl+C) to quit.")
    _idle(server)


if __name__ == "__main__":
    main()
