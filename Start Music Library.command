#!/bin/bash
# Alternative launcher (if you prefer not to use the .app).
# Keep this next to music_library.py and app.html.
cd "$(dirname "$0")" || exit 1
PY=""
for c in python3 /usr/bin/python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  osascript -e 'display dialog "Python 3 was not found. Install it from python.org." buttons {"OK"} with title "DJ Music Library"'; exit 1
fi
# tag reader (required)
if ! "$PY" -c "import mutagen" >/dev/null 2>&1; then
  echo "Installing mutagen..."; "$PY" -m ensurepip >/dev/null 2>&1
  "$PY" -m pip install --user mutagen >/dev/null 2>&1 || "$PY" -m pip install --break-system-packages mutagen >/dev/null 2>&1
fi
# native window toolkit (optional — gives a real window instead of a browser)
if ! "$PY" -c "import webview" >/dev/null 2>&1; then
  echo "Setting up the app window (one-time)..."
  "$PY" -m pip install --user pywebview >/dev/null 2>&1 || "$PY" -m pip install --break-system-packages pywebview >/dev/null 2>&1
fi
"$PY" music_library.py
