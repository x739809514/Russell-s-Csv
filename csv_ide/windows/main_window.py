import csv
import os
import shlex
import subprocess
import sys
from typing import Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from csv_ide.models import CsvDocument
from csv_ide.theme import apply_theme
from csv_ide.widgets.cell_detail import CellDetailPanel
from csv_ide.widgets.editor import EditorWidget
from csv_ide.widgets.find_panel import FindPanel
from csv_ide.widgets.relation_panel import RelationPanel
from csv_ide.widgets.replace_dialog import ReplaceDialog


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("RussellCsv")
        self.resize(1200, 720)
        self._settings = QtCore.QSettings("RussellCsv", "RussellCsv")
        self._theme_name = self._settings.value("ui_theme", "light", type=str)
        self._plugin_scripts = self._settings.value("plugin_scripts", [], type=list)
        self._plugin_processes: list[QtCore.QProcess] = []

        splitter = QtWidgets.QSplitter(self)
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        left_panel = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        self._search_input = QtWidgets.QLineEdit(self)
        self._search_input.setPlaceholderText("Filter files...")
        self._file_list = QtWidgets.QListWidget(self)
        self._file_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
        self._file_list.itemDoubleClicked.connect(self._open_from_list)
        self._file_list.customContextMenuRequested.connect(self._show_file_list_menu)
        self._search_input.textChanged.connect(self._filter_file_list)
        left_layout.addWidget(self._search_input)
        left_layout.addWidget(self._file_list)

        self._tabs = QtWidgets.QTabWidget(self)
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(False)
        self._tabs.tabCloseRequested.connect(self.close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        right_panel = QtWidgets.QTabWidget(self)
        relation_panel = RelationPanel(self)
        self._find_panel = FindPanel(self)
        self._cell_panel = CellDetailPanel(self)
        right_panel.addTab(relation_panel, "Relationship Graph")
        right_panel.addTab(self._find_panel, "Find")
        right_panel.addTab(self._cell_panel, "Cell")

        splitter.addWidget(left_panel)
        splitter.addWidget(self._tabs)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 1)

        self.setCentralWidget(splitter)
        self._status_bar = self.statusBar()
        self._status_bar.showMessage("Ready")

        self._open_documents: dict[str, EditorWidget] = {}
        self._root_path = QtCore.QDir.currentPath()
        self._right_tabs = right_panel
        self._current_path: Optional[str] = None
        self._ignore_selection_change = False
        self._replace_dialog: Optional[ReplaceDialog] = None
        self._file_comments = self._load_file_comments()
        self._build_actions()
        self._root_path = self._settings.value("last_root_path", self._root_path, type=str)
        self._apply_theme(self._theme_name)
        self.open_folder(self._root_path)
        self._restore_session_state()

    def _open_from_list(self, item: QtWidgets.QListWidgetItem) -> None:
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(path, str):
            self.open_file(path)

    def _on_file_selection_changed(self) -> None:
        if self._ignore_selection_change:
            return
        item = self._file_list.currentItem()
        if not item:
            return
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(path, str):
            return
        self._persist_session_state()

    def open_file(self, path: str) -> None:
        if path in self._open_documents:
            widget = self._open_documents[path]
            self._show_tab(widget)
            self._persist_session_state()
            return

        delimiter = "\t" if path.lower().endswith(".tsv") else ","
        try:
            document = self._load_document(path, delimiter)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, "Open failed", str(exc))
            return

        editor = EditorWidget(document, self)
        editor.document_changed.connect(self._on_document_changed)
        editor.cell_selected.connect(
            lambda row, col, value, ed=editor: self._cell_panel.update_cell(ed, row, col, value)
        )
        self._open_documents[path] = editor

        self._show_tab(editor)
        self._persist_session_state()
        editor._table_view.selectionModel().selectionChanged.connect(
            lambda *_: self._update_status(editor)
        )

    def _build_actions(self) -> None:
        new_action = QtGui.QAction("New", self)
        new_action.setShortcut(QtGui.QKeySequence.StandardKey.New)
        new_action.triggered.connect(self.new_file)

        open_action = QtGui.QAction("Open File...", self)
        open_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file_dialog)

        open_folder_action = QtGui.QAction("Open Folder...", self)
        open_folder_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+O"))
        open_folder_action.triggered.connect(self.open_folder_dialog)

        open_terminal_action = QtGui.QAction("Open Terminal Here", self)
        open_terminal_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+T"))
        open_terminal_action.triggered.connect(self.open_terminal_here)
        open_terminal_action.setShortcutVisibleInContextMenu(True)

        save_action = QtGui.QAction("Save", self)
        save_action.setShortcut(QtGui.QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_current)
        save_action.setShortcutVisibleInContextMenu(True)

        save_as_action = QtGui.QAction("Save As...", self)
        save_as_action.setShortcut(QtGui.QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_as_current)
        save_as_action.setShortcutVisibleInContextMenu(True)

        save_copy_action = QtGui.QAction("Save Copy...", self)
        save_copy_action.setShortcut(QtGui.QKeySequence("Ctrl+Alt+S"))
        save_copy_action.triggered.connect(self.save_copy_current)
        save_copy_action.setShortcutVisibleInContextMenu(True)

        save_all_action = QtGui.QAction("Save All", self)
        save_all_action.setShortcut(QtGui.QKeySequence("Ctrl+Shift+S"))
        save_all_action.triggered.connect(self.save_all)
        save_all_action.setShortcutVisibleInContextMenu(True)

        rename_action = QtGui.QAction("Rename File...", self)
        rename_action.setShortcut(QtGui.QKeySequence("F2"))
        rename_action.triggered.connect(self.rename_current)
        rename_action.setShortcutVisibleInContextMenu(True)

        close_action = QtGui.QAction("Close File", self)
        close_action.setShortcut(QtGui.QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close_current_tab)
        close_action.setShortcutVisibleInContextMenu(True)

        undo_action = QtGui.QAction("Undo", self)
        undo_action.setShortcut(QtGui.QKeySequence.StandardKey.Undo)
        undo_action.triggered.connect(self.undo_current)
        undo_action.setShortcutVisibleInContextMenu(True)

        redo_action = QtGui.QAction("Redo", self)
        redo_action.setShortcut(QtGui.QKeySequence.StandardKey.Redo)
        redo_action.triggered.connect(self.redo_current)
        redo_action.setShortcutVisibleInContextMenu(True)

        insert_row_above_action = QtGui.QAction("Insert Row Above", self)
        insert_row_above_action.triggered.connect(lambda: self._apply_to_current("insert_row_above"))
        insert_row_above_action.setShortcut(QtGui.QKeySequence("Meta+I"))
        insert_row_above_action.setShortcutVisibleInContextMenu(True)

        insert_row_below_action = QtGui.QAction("Insert Row Below", self)
        insert_row_below_action.triggered.connect(lambda: self._apply_to_current("insert_row_below"))
        insert_row_below_action.setShortcut(QtGui.QKeySequence("Meta+K"))
        insert_row_below_action.setShortcutVisibleInContextMenu(True)

        delete_rows_action = QtGui.QAction("Delete Row(s)", self)
        delete_rows_action.triggered.connect(lambda: self._apply_to_current("delete_rows"))
        delete_rows_action.setShortcuts(
            [QtGui.QKeySequence("Ctrl+Backspace"), QtGui.QKeySequence("Meta+Backspace")]
        )
        delete_rows_action.setShortcutVisibleInContextMenu(True)

        insert_col_left_action = QtGui.QAction("Insert Column Left", self)
        insert_col_left_action.triggered.connect(lambda: self._apply_to_current("insert_col_left"))
        insert_col_left_action.setShortcut(QtGui.QKeySequence("Meta+J"))
        insert_col_left_action.setShortcutVisibleInContextMenu(True)

        insert_col_right_action = QtGui.QAction("Insert Column Right", self)
        insert_col_right_action.triggered.connect(lambda: self._apply_to_current("insert_col_right"))
        insert_col_right_action.setShortcut(QtGui.QKeySequence("Meta+L"))
        insert_col_right_action.setShortcutVisibleInContextMenu(True)

        delete_cols_action = QtGui.QAction("Delete Column(s)", self)
        delete_cols_action.triggered.connect(lambda: self._apply_to_current("delete_cols"))
        delete_cols_action.setShortcuts(
            [QtGui.QKeySequence("Ctrl+Shift+Backspace"), QtGui.QKeySequence("Meta+Shift+Backspace")]
        )
        delete_cols_action.setShortcutVisibleInContextMenu(True)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(open_folder_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addAction(save_copy_action)
        file_menu.addAction(save_all_action)
        file_menu.addSeparator()
        file_menu.addAction(rename_action)
        file_menu.addAction(close_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(undo_action)
        edit_menu.addAction(redo_action)
        edit_menu.addSeparator()
        find_action = QtGui.QAction("Find...", self)
        find_action.setShortcut(QtGui.QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.open_find_panel)
        find_action.setShortcutVisibleInContextMenu(True)
        replace_action = QtGui.QAction("Replace...", self)
        replace_action.setShortcut(QtGui.QKeySequence.StandardKey.Replace)
        replace_action.triggered.connect(self.open_replace_dialog)
        replace_action.setShortcutVisibleInContextMenu(True)
        edit_menu.addAction(find_action)
        edit_menu.addAction(replace_action)
        edit_menu.addSeparator()
        edit_menu.addAction(insert_row_above_action)
        edit_menu.addAction(insert_row_below_action)
        edit_menu.addAction(delete_rows_action)
        edit_menu.addSeparator()
        edit_menu.addAction(insert_col_left_action)
        edit_menu.addAction(insert_col_right_action)
        edit_menu.addAction(delete_cols_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(open_terminal_action)

        self._plugin_menu = self.menuBar().addMenu("Plugin")
        add_plugin_action = QtGui.QAction("Add Script...", self)
        add_plugin_action.triggered.connect(self._add_plugin_scripts)
        self._plugin_menu.addAction(add_plugin_action)
        self._plugin_menu.addSeparator()
        self._rebuild_plugin_menu()

        view_menu = self.menuBar().addMenu("View")
        light_theme_action = QtGui.QAction("Light Theme", self)
        light_theme_action.setCheckable(True)
        dark_theme_action = QtGui.QAction("Dark Theme", self)
        dark_theme_action.setCheckable(True)
        theme_group = QtGui.QActionGroup(self)
        theme_group.setExclusive(True)
        theme_group.addAction(light_theme_action)
        theme_group.addAction(dark_theme_action)
        light_theme_action.triggered.connect(lambda: self._set_theme("light"))
        dark_theme_action.triggered.connect(lambda: self._set_theme("dark"))
        if self._theme_name == "dark":
            dark_theme_action.setChecked(True)
        else:
            light_theme_action.setChecked(True)
        view_menu.addAction(light_theme_action)
        view_menu.addAction(dark_theme_action)

        # Ensure shortcuts work even when focus is in the table widget.
        for action in (
            new_action,
            open_action,
            open_folder_action,
            open_terminal_action,
            save_action,
            save_as_action,
            save_copy_action,
            save_all_action,
            rename_action,
            close_action,
            undo_action,
            redo_action,
            find_action,
            replace_action,
            insert_row_above_action,
            insert_row_below_action,
            delete_rows_action,
            insert_col_left_action,
            insert_col_right_action,
            delete_cols_action,
        ):
            action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            self.addAction(action)

    def _set_theme(self, name: str) -> None:
        if name not in {"light", "dark"}:
            return
        if name == self._theme_name:
            return
        self._theme_name = name
        self._settings.setValue("ui_theme", name)
        self._apply_theme(name)

    def _apply_theme(self, name: str) -> None:
        app = QtWidgets.QApplication.instance()
        if not app:
            return
        apply_theme(app, name)

    def _apply_to_current(self, method_name: str) -> None:
        editor = self._current_editor()
        if editor and hasattr(editor, method_name):
            getattr(editor, method_name)()

    def _current_editor(self) -> Optional[EditorWidget]:
        widget = self._tabs.currentWidget()
        if isinstance(widget, EditorWidget):
            return widget
        return None

    def _load_document(self, path: str, delimiter: str) -> CsvDocument:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            rows = list(reader)
        if not rows:
            return CsvDocument(path, delimiter, [], [])
        header = rows[0]
        expected_cols = len(header)
        for idx, row in enumerate(rows[1:], start=2):
            if len(row) != expected_cols:
                raise ValueError(f"Line {idx} has {len(row)} columns, expected {expected_cols}.")
        return CsvDocument(path, delimiter, header, rows[1:])

    def new_file(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "New CSV File",
            self._root_path,
            "CSV Files (*.csv *.tsv)",
        )
        if not path:
            return
        if not path.lower().endswith((".csv", ".tsv")):
            path += ".csv"
        delimiter = "\t" if path.lower().endswith(".tsv") else ","
        document = CsvDocument(path, delimiter, ["column1"], [])
        editor = EditorWidget(document, self)
        editor.document_changed.connect(self._on_document_changed)
        self._open_documents[path] = editor
        self._show_tab(editor)
        self.save_current()

    def open_file_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open CSV File",
            self._root_path,
            "CSV Files (*.csv *.tsv)",
        )
        if path:
            self.open_file(path)

    def open_folder_dialog(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Folder", self._root_path)
        if path:
            self.open_folder(path)

    def open_find_panel(self) -> None:
        self._right_tabs.setCurrentIndex(1)
        self._find_panel.focus_input()

    def open_replace_dialog(self) -> None:
        if self._replace_dialog is None:
            self._replace_dialog = ReplaceDialog(self)
        self._replace_dialog.show()
        self._replace_dialog.raise_()
        self._replace_dialog.activateWindow()

    def open_folder(self, path: str) -> None:
        self._root_path = path
        self._settings.setValue("last_root_path", path)
        self._populate_file_list(path)

    def open_terminal_here(self) -> None:
        if not self._root_path:
            return
        quoted = shlex.quote(self._root_path)
        script = (
            'tell application "Terminal"\n'
            "activate\n"
            f'do script "cd {quoted}"\n'
            "end tell"
        )
        try:
            subprocess.run(["osascript", "-e", script], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            QtWidgets.QMessageBox.warning(self, "Terminal failed", str(exc))

    def _add_plugin_scripts(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Add Python Script",
            self._root_path,
            "Python Files (*.py)",
        )
        if not paths:
            return
        current = {path for path in self._plugin_scripts if isinstance(path, str)}
        for path in paths:
            if path not in current:
                current.add(path)
        self._plugin_scripts = sorted(current)
        self._settings.setValue("plugin_scripts", self._plugin_scripts)
        self._rebuild_plugin_menu()

    def _rebuild_plugin_menu(self) -> None:
        if not hasattr(self, "_plugin_menu"):
            return
        actions = self._plugin_menu.actions()
        keep = set(actions[:2])
        for action in actions:
            if action not in keep:
                self._plugin_menu.removeAction(action)
        for path in self._plugin_scripts:
            if not isinstance(path, str):
                continue
            label = os.path.splitext(os.path.basename(path))[0] or path
            action = QtGui.QAction(label, self)
            action.setToolTip(path)
            action.triggered.connect(lambda _, p=path: self._run_plugin_script(p))
            self._plugin_menu.addAction(action)

    def _run_plugin_script(self, path: str) -> None:
        if not os.path.exists(path):
            QtWidgets.QMessageBox.warning(self, "Plugin failed", f"Script not found:\n{path}")
            return
        process = QtCore.QProcess(self)
        process.setProgram(sys.executable)
        process.setArguments([path])
        process.setWorkingDirectory(self._root_path)
        process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.SeparateChannels)
        self._plugin_processes.append(process)

        def _cleanup() -> None:
            if process in self._plugin_processes:
                self._plugin_processes.remove(process)
            process.deleteLater()

        def _read_text(data: QtCore.QByteArray) -> str:
            if not data:
                return ""
            return bytes(data).decode("utf-8", errors="replace").strip()

        def _on_finished(exit_code: int, exit_status: QtCore.QProcess.ExitStatus) -> None:
            stdout_text = _read_text(process.readAllStandardOutput())
            stderr_text = _read_text(process.readAllStandardError())
            if exit_status != QtCore.QProcess.ExitStatus.NormalExit or exit_code != 0:
                message = "Script failed."
                details = stderr_text or stdout_text
                if details:
                    message = f"{message}\n\n{details}"
                QtWidgets.QMessageBox.warning(self, "Plugin failed", message)
            else:
                message = "Script finished successfully."
                if stdout_text:
                    message = f"{message}\n\n{stdout_text}"
                QtWidgets.QMessageBox.information(self, "Plugin finished", message)
            _cleanup()

        def _on_error(_: QtCore.QProcess.ProcessError) -> None:
            details = _read_text(process.readAllStandardError())
            message = "Script failed to start."
            if details:
                message = f"{message}\n\n{details}"
            QtWidgets.QMessageBox.warning(self, "Plugin failed", message)
            _cleanup()

        process.finished.connect(_on_finished)
        process.errorOccurred.connect(_on_error)
        process.start()

    def save_current(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        self._save_editor(editor, editor.document.path, update_path=False)

    def save_as_current(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save CSV As",
            editor.document.path,
            "CSV Files (*.csv *.tsv)",
        )
        if path:
            self._save_editor(editor, path, update_path=True)

    def save_copy_current(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Copy",
            editor.document.path,
            "CSV Files (*.csv *.tsv)",
        )
        if path:
            self._save_editor(editor, path, update_path=False)

    def save_all(self) -> None:
        for editor in list(self._open_documents.values()):
            if editor.is_dirty():
                if not self._save_editor(editor, editor.document.path, update_path=False):
                    return
        self._status_bar.showMessage("Saved all open files")

    def rename_current(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        current_path = editor.document.path
        directory = os.path.dirname(current_path)
        base = os.path.basename(current_path)
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename File", "New file name:", text=base
        )
        if not ok or not new_name:
            return
        new_path = os.path.join(directory, new_name)
        if os.path.exists(new_path):
            QtWidgets.QMessageBox.warning(self, "Rename failed", "File already exists.")
            return
        try:
            os.rename(current_path, new_path)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Rename failed", str(exc))
            return
        if current_path in self._file_comments:
            self._file_comments[new_path] = self._file_comments.pop(current_path)
            self._persist_file_comments()
        editor.document.path = new_path
        self._open_documents.pop(current_path, None)
        self._open_documents[new_path] = editor
        self._update_window_title(editor)
        self._update_list_item_path(current_path, new_path)
        self._status_bar.showMessage(f"Renamed to: {os.path.basename(new_path)}")

    def close_current_tab(self) -> None:
        index = self._tabs.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def close_tab(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if not isinstance(widget, EditorWidget):
            return
        editor = widget
        if editor.is_dirty():
            if not self._confirm_discard(editor):
                return
        path = editor.document.path
        self._open_documents.pop(path, None)
        self._tabs.removeTab(index)
        editor.deleteLater()
        if self._tabs.count() == 0:
            self._current_path = None
            self._update_window_title(None)
            self._cell_panel.clear()
        self._persist_session_state()

    def undo_current(self) -> None:
        editor = self._current_editor()
        if editor:
            editor.undo()

    def redo_current(self) -> None:
        editor = self._current_editor()
        if editor:
            editor.redo()

    def _on_document_changed(self, path: str) -> None:
        editor = self._open_documents.get(path)
        if editor:
            self._update_status(editor)
            self._update_window_title(editor)

    def _update_status(self, editor: EditorWidget) -> None:
        doc = editor.document
        rows = len(doc.rows)
        cols = len(doc.header)
        selection = editor._table_view.selectionModel().selection()
        selected_cells = sum(
            (range_.right() - range_.left() + 1) * (range_.bottom() - range_.top() + 1)
            for range_ in selection
        )
        self._status_bar.showMessage(
            f"UTF-8 | Rows: {rows} | Cols: {cols} | Selected: {selected_cells}"
        )

    def _update_window_title(self, editor: Optional[EditorWidget]) -> None:
        if not editor:
            self.setWindowTitle("RussellCsv")
            return
        name = os.path.basename(editor.document.path)
        if editor.is_dirty():
            name = f"*{name}"
        self.setWindowTitle(f"{name} - RussellCsv")
        self._update_tab_label(editor)

    def _update_tab_label(self, editor: EditorWidget) -> None:
        index = self._tab_index_for_editor(editor)
        if index == -1:
            return
        label = os.path.basename(editor.document.path)
        if editor.is_dirty():
            label = f"*{label}"
        self._tabs.setTabText(index, label)

    def _tab_index_for_editor(self, editor: EditorWidget) -> int:
        for idx in range(self._tabs.count()):
            if self._tabs.widget(idx) is editor:
                return idx
        return -1

    def _show_tab(self, editor: EditorWidget) -> None:
        index = self._tab_index_for_editor(editor)
        if index == -1:
            label = os.path.basename(editor.document.path)
            if editor.is_dirty():
                label = f"*{label}"
            index = self._tabs.addTab(editor, label)
        self._tabs.setCurrentIndex(index)
        self._activate_editor(editor)

    def _on_tab_changed(self, index: int) -> None:
        widget = self._tabs.widget(index)
        if not isinstance(widget, EditorWidget):
            self._current_path = None
            self._update_window_title(None)
            self._cell_panel.clear()
            return
        self._activate_editor(widget)

    def _activate_editor(self, editor: EditorWidget) -> None:
        self._current_path = editor.document.path
        self._update_status(editor)
        self._update_window_title(editor)
        current = editor._table_view.selectionModel().currentIndex()
        if current.isValid():
            row = current.row()
            col = current.column()
            value = editor._cell_text(row, col)
            self._cell_panel.update_cell(editor, row, col, value)

    def _confirm_discard(self, editor: EditorWidget) -> bool:
        result = QtWidgets.QMessageBox.question(
            self,
            "Unsaved Changes",
            f"Save changes to {os.path.basename(editor.document.path)}?",
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if result == QtWidgets.QMessageBox.StandardButton.Save:
            return self._save_editor(editor, editor.document.path, update_path=False)
        if result == QtWidgets.QMessageBox.StandardButton.Discard:
            return True
        return False

    def _save_editor(self, editor: EditorWidget, path: str, update_path: bool) -> bool:
        if not editor.sync_from_code_view():
            return False
        doc = editor.document
        delimiter = "\t" if path.lower().endswith(".tsv") else ","
        if not path.lower().endswith((".csv", ".tsv")):
            path += ".csv"
            delimiter = ","
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter=delimiter)
                if doc.header:
                    writer.writerow(doc.header)
                writer.writerows(doc.rows)
            if update_path:
                old_path = doc.path
                doc.path = path
                doc.delimiter = delimiter
                self._open_documents.pop(old_path, None)
                self._open_documents[path] = editor
                self._update_list_item_path(old_path, path)
                if self._current_path == old_path:
                    self._current_path = path
            editor.set_dirty(False)
            self._update_window_title(editor)
            self._status_bar.showMessage(f"Saved: {os.path.basename(path)}")
            return True
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, "Save failed", str(exc))
            return False

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        for editor in list(self._open_documents.values()):
            if editor.is_dirty():
                if not self._confirm_discard(editor):
                    event.ignore()
                    return
        self._persist_session_state()
        event.accept()

    def _populate_file_list(self, root_path: str) -> None:
        self._file_list.clear()
        entries: list[tuple[str, str]] = []
        for root, _, files in os.walk(root_path):
            for name in files:
                _, ext = os.path.splitext(name)
                if ext.lower() in {".csv", ".tsv"}:
                    full_path = os.path.join(root, name)
                    entries.append((name, full_path))
        for name, full_path in sorted(entries, key=lambda item: item[0].lower()):
            item = QtWidgets.QListWidgetItem(name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, full_path)
            item.setToolTip(self._item_tooltip(full_path))
            self._file_list.addItem(item)

    def _filter_file_list(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            name = item.text().lower()
            path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            comment = ""
            if isinstance(path, str):
                comment = self._file_comments.get(path, "").lower()
            match = text in name or (comment and text in comment)
            item.setHidden(bool(text) and not match)

    def _select_path(self, path: str) -> None:
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            item_path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if item_path == path:
                self._file_list.setCurrentItem(item)
                return

    def _update_list_item_path(self, old_path: str, new_path: str) -> None:
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            item_path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if item_path == old_path:
                item.setText(os.path.basename(new_path))
                item.setData(QtCore.Qt.ItemDataRole.UserRole, new_path)
                item.setToolTip(self._item_tooltip(new_path))
                return

    def _persist_session_state(self) -> None:
        self._settings.setValue("last_root_path", self._root_path)
        self._settings.setValue("last_open_files", list(self._open_documents.keys()))
        self._settings.setValue("last_current_file", self._current_path or "")
        self._settings.setValue("last_selected_files", self._selected_paths())

    def _restore_session_state(self) -> None:
        last_selected = self._settings.value("last_selected_files", [], type=list)
        last_current = self._settings.value("last_current_file", "", type=str)
        if last_selected:
            self._ignore_selection_change = True
            self._select_paths(last_selected)
            self._ignore_selection_change = False
        if last_current:
            self.open_file(last_current)
        elif last_selected:
            self.open_file(last_selected[0])

    def _selected_paths(self) -> list[str]:
        paths: list[str] = []
        for item in self._file_list.selectedItems():
            path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(path, str):
                paths.append(path)
        return paths

    def _select_paths(self, paths: list[str]) -> None:
        target = set(paths)
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if path in target:
                item.setSelected(True)

    def _show_file_list_menu(self, position: QtCore.QPoint) -> None:
        item = self._file_list.itemAt(position)
        if not item:
            return
        path = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(path, str):
            return
        menu = QtWidgets.QMenu(self)
        add_comment = menu.addAction("Add Comment")
        remove_comment = menu.addAction("Remove Comment")
        add_comment.triggered.connect(lambda: self._add_comment_for_item(item, path))
        remove_comment.triggered.connect(lambda: self._remove_comment_for_item(item, path))
        remove_comment.setEnabled(path in self._file_comments)
        menu.exec(self._file_list.viewport().mapToGlobal(position))

    def _add_comment_for_item(self, item: QtWidgets.QListWidgetItem, path: str) -> None:
        current = self._file_comments.get(path, "")
        comment, ok = QtWidgets.QInputDialog.getText(
            self, "Add Comment", "Comment:", text=current
        )
        if not ok:
            return
        comment = comment.strip()
        if comment:
            self._file_comments[path] = comment
        else:
            self._file_comments.pop(path, None)
        self._persist_file_comments()
        item.setToolTip(self._item_tooltip(path))

    def _remove_comment_for_item(self, item: QtWidgets.QListWidgetItem, path: str) -> None:
        if path in self._file_comments:
            self._file_comments.pop(path, None)
            self._persist_file_comments()
        item.setToolTip(self._item_tooltip(path))

    def _item_tooltip(self, path: str) -> str:
        return self._file_comments.get(path, "None")

    def _load_file_comments(self) -> dict[str, str]:
        raw = self._settings.value("file_comments", {}, type=dict)
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items() if value is not None}

    def _persist_file_comments(self) -> None:
        self._settings.setValue("file_comments", self._file_comments)
