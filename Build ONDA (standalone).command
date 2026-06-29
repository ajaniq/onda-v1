#!/bin/bash
# ============================================================================
#  Build a STANDALONE ONDA.app  (bundles Python + everything — recipients
#  need NO Python, NO pip, NO internet).  Run this ONCE on your Mac.
#
#  HOW TO USE:
#   1. Keep this file in the SAME folder as: music_library.py, app.html,
#      logo.png, icon.icns
#   2. Right-click this file -> Open -> Open  (first time only)
#   3. Wait a couple of minutes. The finished app appears in the "dist" folder
#      as ONDA.app (and a zipped ONDA-standalone.zip you can share).
# ============================================================================
set -e
cd "$(dirname "$0")"

echo "==> Checking files..."
for f in music_library.py app.html logo.png icon.icns; do
  [ -f "$f" ] || { echo "MISSING: $f  (keep all source files next to this script)"; read -r -p "Press Return to close..."; exit 1; }
done

PY=""
for c in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3 /usr/bin/python3; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -z "$PY" ] && { echo "Python 3 not found. Install it from https://www.python.org/downloads/ and re-run."; read -r -p "Press Return..."; exit 1; }

echo "==> Creating a clean build environment..."
rm -rf .ondabuild build dist *.spec
"$PY" -m venv .ondabuild
source .ondabuild/bin/activate
python -m pip install --upgrade pip wheel >/dev/null
echo "==> Installing build tools (PyInstaller, pywebview, mutagen)..."
python -m pip install pyinstaller pywebview mutagen >/dev/null

echo "==> Building ONDA.app (this can take a minute or two)..."
pyinstaller --noconfirm --windowed --name ONDA \
  --icon icon.icns \
  --add-data "app.html:." \
  --add-data "logo.png:." \
  --collect-all webview \
  --collect-all mutagen \
  --osx-bundle-identifier com.onda.musiclibrary \
  music_library.py
deactivate

echo "==> Zipping for sharing..."
( cd dist && zip -q -r "ONDA-standalone.zip" "ONDA.app" )

echo ""
echo "✅ Done!"
echo "   App:   $(pwd)/dist/ONDA.app"
echo "   Share: $(pwd)/dist/ONDA-standalone.zip"
open dist
