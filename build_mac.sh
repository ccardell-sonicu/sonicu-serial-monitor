#!/bin/bash
# Builds the double-clickable macOS app into dist/.
# The app runs on the same CPU type as the Python used to build it; to build
# for Intel Macs on Apple Silicon, point PYTHON at an x86_64 Python, e.g.
#   PYTHON=/Library/Frameworks/Python.framework/Versions/3.9/bin/python3 ./build_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
ARCH=$("$PYTHON" -c "import platform; print(platform.machine())")
NAME="Sonicu Serial Monitor"
VENV=".venv-build-$ARCH"

"$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r requirements.txt pyinstaller
"$VENV/bin/pyinstaller" --onefile --console --noconfirm --name "$NAME" \
    --distpath "dist/mac-$ARCH" --workpath "build/$ARCH" --specpath "build/$ARCH" \
    serial_monitor.py

# Zip with ditto so the executable permission survives download/unzip.
ZIP="dist/Sonicu-Serial-Monitor-mac-$ARCH.zip"
rm -f "$ZIP"
ditto -c -k --norsrc --noextattr --noacl "dist/mac-$ARCH/$NAME" "$ZIP"
echo "Built: $ZIP"
