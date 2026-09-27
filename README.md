# RussellCsv

RussellCsv is a lightweight CSV/TSV IDE built with PyQt6. It provides a multi-tab spreadsheet-style editor with file browsing, search/filtering, and quick inspection tools to make working with large CSVs easier.

## Features
- Multi-tab CSV/TSV editing with file list filtering
- Find and replace panel plus cell detail inspector
- Auto-save and session restore
- Optional HTML preview and relation editor dialogs

## Install and run
### macOS app (recommended)
Build once on a Mac with Python 3 installed:

```bash
./build-macos.sh
```

Open `dist/RussellCsv.app` in Finder, or drag it to `/Applications`. Launching the app does **not** open Terminal or require a separate Python installation. The build script installs dependencies into `.build-venv` and packages them with the app; run it again after updating the source. The `.app` is generated locally and is not stored in GitHub.

Build on each target architecture (Apple Silicon or Intel). Local builds are not notarized; distributing the app without Gatekeeper warnings requires Apple Developer ID signing and notarization.

### macOS command launcher
Double-click `CSV-IDE.command` to run the Python version in Terminal. It creates `.venv` and installs dependencies on first launch.

### Manual Python launch
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## QA contact
For questions or QA feedback, email: russell.xin@yahoo.com
