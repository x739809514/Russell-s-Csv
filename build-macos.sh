#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This build must run on macOS." >&2
  exit 1
fi

python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements.txt 'pyinstaller==6.22.3'
.build-venv/bin/python -m PyInstaller \
  --noconfirm --clean --windowed \
  --name RussellCsv \
  --osx-bundle-identifier com.russellcsv.app \
  main.py

echo "App: $ROOT_DIR/dist/RussellCsv.app"
