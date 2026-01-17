# RussellCsv Detailed Guide

This document provides a comprehensive overview of RussellCsv, including features, UI layout, and step-by-step usage.

## Overview
RussellCsv is a PyQt6-based CSV/TSV desktop editor. It offers a spreadsheet-style grid, a raw code view, batch editing tools, find/replace, relation visualization, and safe backups for large CSV workflows.

## Install and launch
### Option 1: macOS launcher
1. Double-click `CSV-IDE.command`
2. On first run it creates `.venv` and installs dependencies
3. The app launches automatically

### Option 2: manual
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## UI layout
- Left: file list and filter box
- Center: multi-tab editor (Grid / Code views)
- Right: tool panels (Find / Cell)
- Bottom: status bar (encoding, row/column counts, selected cell count)
- Top menu: File / Edit / Tools / Plugin / View / Help

## Basic workflow
### 1) Open a workspace folder
- `File > Open Folder...`
- The left list shows all `.csv` / `.tsv` files under that folder

### 2) Open or create files
- Double-click a file in the list to open
- `File > Open File...` opens a specific file
- `File > New` creates a new file (default header `column1`)

### 3) Save
- `File > Save` saves the current file
- `File > Save As...` saves to a new path and updates the tab
- `File > Save Copy...` saves a copy without changing the active file
- `File > Save All` saves all modified open files

### 4) Rename
- `File > Rename File...` renames the current file on disk

### 5) Close and restore
- Closing a tab prompts to save unsaved changes
- On exit, the app persists last opened files and selection
- Next launch restores the previous session

## Editing features
### 1) Grid view (table editing)
- Direct cell editing
- `Delete/Backspace` clears selected cells
- Table right-click menu:
  - Insert Row Above / Below
  - Delete Row(s)
  - Insert Column Left / Right
  - Delete Column(s)
- Row/column header right-click menu:
  - Insert row/column
  - Delete row/column
  - Rename Column (or double-click column header)

### 2) Code view (raw CSV text)
- Edit as plain CSV text
- Switching back to Grid re-parses the content
- Row/column mismatch triggers a CSV Parse Error

### 3) Undo / Redo
- `Edit > Undo / Redo`
- Supports grid edits and insert/delete operations

### 4) Incremental fill
- Select multiple cells in the same column while holding `Alt`
- If the anchor value matches `prefix + number + suffix` (e.g. `item_001`)
  the app auto-increments values by row offset

## Find and replace
### Find panel (right side)
- Enter text and click `Find Next`
- `Find All` lists matches; double-click a result to jump
- Optional case-sensitive search

### Replace dialog
- `Edit > Replace...`
- Replace current match or replace all
- Optional case-sensitive match

## Cell panel (right side)
- Shows current cell location and value
- Edit value and click `Apply`
- Supports multi-cell updates
- `Increment` applies numeric increments when values are integers
- Press `Enter` to apply (`Shift+Enter` inserts a newline)

## File list and filtering
- Filter by filename or comment text
- Right-click a file to add/remove a comment
- Comments are used for filtering and shown as tooltips

## Auto Save
- Toggle `Auto Save` under the file list
- Triggers on tab switch, focus loss, or app deactivation
- Status bar shows auto-save results

## Safe Mode (automatic backups)
Entry: `Tools > Safe Mode...`

Safe Mode periodically copies selected CSV files to a backup folder and maintains a backup log.

Setup:
1. Set backup interval in minutes
2. Choose a backup folder
3. Add CSV/TSV files to protect
4. Use `Backup Now` for an immediate run

Backup management:
- Log shows timestamp and backup path
- `Reload Selected Backup` overwrites the original file
- Delete selected backups from disk

Note: Safe Mode only runs when interval, backup folder, and file list are all set.

## Relations and graph
### Relation editor
Entry: `Tools > Edit Relations...`

Use this to define relations between tables, saved to `relations.json`.

Steps:
1. Open a CSV file (becomes the current table)
2. Choose a field from the current table
3. Select a target table and field
4. Choose relation type (`one_to_one` or `one_to_many`)
5. Click `Add Relation`

Header row setting:
- Enter `head` or a row number (e.g. `4`) to determine header row

### Relationship graph
Entry: `Tools > Relationship Graph...`

- Visualizes relations as a graph
- Nodes are draggable and layout is saved to `relation_layout.json`

### Import relation config
Entry: `Tools > Import Relation Config...`

- Imports `relations` or layout `nodes` from JSON
- Writes to `relations.json` and/or `relation_layout.json`

## HTML preview
The app includes an HTML preview window used by graph visualization.
- Full HTML content is rendered as-is
- Mermaid-like `graph` / `flowchart` text is rendered as a simple diagram
- Supports pan/zoom and drag for nodes when enabled

## Plugin scripts
Entry: `Plugin > Add Script...`

- Add local Python scripts to the Plugin menu
- Run a script by clicking its name
- Output or errors are shown in a dialog
- Script working directory is the current workspace

## Themes
Entry: `View > Light Theme / Dark Theme`

- Switch between light and dark themes
- Theme setting persists across sessions

## Data format and limits
- Only `.csv` / `.tsv` supported
- UTF-8 read/write
- First row is the header
- Delimiter is inferred from file extension (`.csv` = `,`, `.tsv` = `\t`)
- Mismatched row length triggers a parse error when leaving Code view

## FAQ
### Q: Why do I get a parse error when switching to Grid?
A: One or more lines have a different column count than the header. Fix or remove extra delimiters.

### Q: Why doesn’t Safe Mode run?
A: You must set interval, backup folder, and add at least one file.

### Q: The relationship graph is empty. Why?
A: Add relations in the Relation Editor first.
