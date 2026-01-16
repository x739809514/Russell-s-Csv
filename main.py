import csv
import io
import json
import math
import os
import shlex
import subprocess
import sys
import traceback
import faulthandler
import signal
from dataclasses import dataclass
from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets, QtWebEngineWidgets


@dataclass
class CsvDocument:
    path: str
    delimiter: str
    header: List[str]
    rows: List[List[str]]


class CSVTableModel(QtCore.QAbstractTableModel):
    def __init__(self, document: CsvDocument, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._document = document

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._document.rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._document.header)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole):
            try:
                return self._document.rows[index.row()][index.column()]
            except IndexError:
                return ""
        return None

    def setData(self, index: QtCore.QModelIndex, value, role: int = QtCore.Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != QtCore.Qt.ItemDataRole.EditRole:
            return False
        while index.row() >= len(self._document.rows):
            self._document.rows.append([""] * len(self._document.header))
        row = self._document.rows[index.row()]
        while index.column() >= len(row):
            row.append("")
        row[index.column()] = str(value)
        self.dataChanged.emit(index, index, [role])
        return True

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return (
            QtCore.Qt.ItemFlag.ItemIsSelectable
            | QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsEditable
        )

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == QtCore.Qt.Orientation.Horizontal:
            if section < len(self._document.header):
                return self._document.header[section]
            return f"Column {section + 1}"
        return str(section + 1)

    def set_document(self, document: CsvDocument) -> None:
        self.beginResetModel()
        self._document = document
        self.endResetModel()

    def insertRows(
        self, row: int, count: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        if parent.isValid() or count <= 0:
            return False
        row = max(0, min(row, len(self._document.rows)))
        self.beginInsertRows(parent, row, row + count - 1)
        for _ in range(count):
            self._document.rows.insert(row, [""] * len(self._document.header))
        self.endInsertRows()
        return True

    def removeRows(
        self, row: int, count: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        if parent.isValid() or count <= 0:
            return False
        if row < 0 or row >= len(self._document.rows):
            return False
        end_row = min(row + count - 1, len(self._document.rows) - 1)
        self.beginRemoveRows(parent, row, end_row)
        del self._document.rows[row : end_row + 1]
        self.endRemoveRows()
        return True

    def insertColumns(
        self, column: int, count: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        if parent.isValid() or count <= 0:
            return False
        column = max(0, min(column, len(self._document.header)))
        self.beginInsertColumns(parent, column, column + count - 1)
        for offset in range(count):
            self._document.header.insert(column + offset, "")
        for row in self._document.rows:
            for offset in range(count):
                row.insert(column + offset, "")
        self.endInsertColumns()
        return True

    def removeColumns(
        self, column: int, count: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> bool:
        if parent.isValid() or count <= 0:
            return False
        if column < 0 or column >= len(self._document.header):
            return False
        end_col = min(column + count - 1, len(self._document.header) - 1)
        self.beginRemoveColumns(parent, column, end_col)
        del self._document.header[column : end_col + 1]
        for row in self._document.rows:
            del row[column : end_col + 1]
        self.endRemoveColumns()
        return True


class EditorWidget(QtWidgets.QWidget):
    document_changed = QtCore.pyqtSignal(str)
    cell_selected = QtCore.pyqtSignal(int, int, str)

    def __init__(self, document: CsvDocument, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._document = document
        self._undo_stack: List[CsvDocument] = []
        self._undo_index = -1
        self._ignore_history = False
        self._dirty = False

        self._toggle_group = QtWidgets.QButtonGroup(self)
        self._grid_button = QtWidgets.QToolButton(self)
        self._grid_button.setText("Grid")
        self._grid_button.setCheckable(True)
        self._code_button = QtWidgets.QToolButton(self)
        self._code_button.setText("Code")
        self._code_button.setCheckable(True)
        self._toggle_group.addButton(self._grid_button)
        self._toggle_group.addButton(self._code_button)
        self._grid_button.setChecked(True)

        toggle_layout = QtWidgets.QHBoxLayout()
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.addWidget(self._grid_button)
        toggle_layout.addWidget(self._code_button)
        toggle_layout.addStretch(1)

        self._stack = QtWidgets.QStackedWidget(self)
        self._table_view = QtWidgets.QTableView(self)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectItems)
        self._table_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table_view.setStyleSheet(
            "QTableView::item:selected { background: #FFD54F; color: #1F1F1F; }"
        )
        self._table_view.horizontalHeader().setStretchLastSection(True)
        self._table_view.verticalHeader().setVisible(True)
        self._table_view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._show_context_menu)
        self._table_view.verticalHeader().setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table_view.horizontalHeader().setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table_view.verticalHeader().customContextMenuRequested.connect(
            self._show_row_header_menu
        )
        self._table_view.horizontalHeader().customContextMenuRequested.connect(
            self._show_col_header_menu
        )
        self._stack.addWidget(self._table_view)

        self._code_edit = QtWidgets.QPlainTextEdit(self)
        self._code_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._stack.addWidget(self._code_edit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(toggle_layout)
        layout.addWidget(self._stack)

        self._model = CSVTableModel(self._document, self)
        self._table_view.setModel(self._model)
        self._table_view.selectionModel().currentChanged.connect(self._on_current_cell_changed)

        self._toggle_group.buttonToggled.connect(self._on_toggle)
        self._code_edit.textChanged.connect(self._on_code_changed)
        self._model.dataChanged.connect(self._on_model_changed)
        self._model.rowsInserted.connect(lambda *_: self._on_model_changed())
        self._model.rowsRemoved.connect(lambda *_: self._on_model_changed())
        self._model.columnsInserted.connect(lambda *_: self._on_model_changed())
        self._model.columnsRemoved.connect(lambda *_: self._on_model_changed())
        self._push_history()

    @property
    def document(self) -> CsvDocument:
        return self._document

    def is_dirty(self) -> bool:
        return self._dirty

    def set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.document_changed.emit(self._document.path)

    def set_document(self, document: CsvDocument) -> None:
        self._document = document
        self._model.set_document(document)
        self._push_history()
        self._dirty = False
        if self._stack.currentIndex() == 1:
            self._code_edit.setPlainText(self._serialize_document())

    def _serialize_document(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=self._document.delimiter)
        if self._document.header:
            writer.writerow(self._document.header)
        writer.writerows(self._document.rows)
        return buffer.getvalue()

    def _parse_csv_text(self, text: str) -> Optional[CsvDocument]:
        reader = csv.reader(io.StringIO(text), delimiter=self._document.delimiter)
        rows = list(reader)
        if not rows:
            return CsvDocument(self._document.path, self._document.delimiter, [], [])
        header = rows[0]
        expected_cols = len(header)
        for idx, row in enumerate(rows[1:], start=2):
            if len(row) != expected_cols:
                raise ValueError(f"Line {idx} has {len(row)} columns, expected {expected_cols}.")
        return CsvDocument(self._document.path, self._document.delimiter, header, rows[1:])

    def _on_toggle(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if not checked:
            return
        if button is self._code_button:
            self._code_edit.blockSignals(True)
            self._code_edit.setPlainText(self._serialize_document())
            self._code_edit.blockSignals(False)
            self._stack.setCurrentIndex(1)
        else:
            text = self._code_edit.toPlainText()
            try:
                parsed = self._parse_csv_text(text)
            except ValueError as exc:
                QtWidgets.QMessageBox.warning(self, "CSV Parse Error", str(exc))
                self._code_button.setChecked(True)
                return
            if parsed is not None:
                self._document = parsed
                self._model.set_document(parsed)
                self._push_history()
                self.document_changed.emit(parsed.path)
            self._stack.setCurrentIndex(0)

    def _on_code_changed(self) -> None:
        if self._stack.currentIndex() == 1:
            self._dirty = True
            self.document_changed.emit(self._document.path)

    def _on_model_changed(self) -> None:
        if not self._ignore_history:
            self._push_history()
        self._dirty = True
        self.document_changed.emit(self._document.path)
        current = self._table_view.selectionModel().currentIndex()
        if current.isValid():
            self._emit_cell_selected(current.row(), current.column())

    def _on_current_cell_changed(
        self, current: QtCore.QModelIndex, _: QtCore.QModelIndex
    ) -> None:
        if current.isValid():
            self._emit_cell_selected(current.row(), current.column())

    def _emit_cell_selected(self, row: int, col: int) -> None:
        value = self._cell_text(row, col)
        self.cell_selected.emit(row, col, value)

    def _snapshot(self) -> CsvDocument:
        header = list(self._document.header)
        rows = [list(row) for row in self._document.rows]
        return CsvDocument(self._document.path, self._document.delimiter, header, rows)

    def _push_history(self) -> None:
        snapshot = self._snapshot()
        if self._undo_index >= 0 and self._undo_index < len(self._undo_stack):
            current = self._undo_stack[self._undo_index]
            if current.header == snapshot.header and current.rows == snapshot.rows:
                return
        if self._undo_index < len(self._undo_stack) - 1:
            self._undo_stack = self._undo_stack[: self._undo_index + 1]
        self._undo_stack.append(snapshot)
        self._undo_index = len(self._undo_stack) - 1

    def can_undo(self) -> bool:
        return self._undo_index > 0

    def can_redo(self) -> bool:
        return self._undo_index < len(self._undo_stack) - 1

    def undo(self) -> None:
        if not self.can_undo():
            return
        self._undo_index -= 1
        self._restore_history(self._undo_stack[self._undo_index])

    def redo(self) -> None:
        if not self.can_redo():
            return
        self._undo_index += 1
        self._restore_history(self._undo_stack[self._undo_index])

    def _restore_history(self, snapshot: CsvDocument) -> None:
        self._ignore_history = True
        self._document = self._snapshot()
        self._document.header = list(snapshot.header)
        self._document.rows = [list(row) for row in snapshot.rows]
        self._model.set_document(self._document)
        self._ignore_history = False
        self._dirty = True
        self.document_changed.emit(self._document.path)

    def insert_row_above(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        row = min((idx.row() for idx in selection), default=0)
        self._model.insertRows(row, 1)

    def insert_row_below(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        row = max((idx.row() for idx in selection), default=-1) + 1
        self._model.insertRows(row, 1)

    def delete_rows(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        if not selection:
            return
        rows = sorted({idx.row() for idx in selection})
        for row in reversed(rows):
            self._model.removeRows(row, 1)

    def insert_col_left(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        col = min((idx.column() for idx in selection), default=0)
        self._model.insertColumns(col, 1)
        self._document.header[col] = self._generate_column_name()
        self._model.headerDataChanged.emit(QtCore.Qt.Orientation.Horizontal, col, col)

    def insert_col_right(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        col = max((idx.column() for idx in selection), default=-1) + 1
        self._model.insertColumns(col, 1)
        self._document.header[col] = self._generate_column_name()
        self._model.headerDataChanged.emit(QtCore.Qt.Orientation.Horizontal, col, col)

    def delete_cols(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        if not selection:
            return
        cols = sorted({idx.column() for idx in selection})
        for col in reversed(cols):
            self._model.removeColumns(col, 1)

    def _generate_column_name(self) -> str:
        base = "new_column"
        existing = {name for name in self._document.header if name}
        if base not in existing:
            return base
        counter = 2
        while f"{base}_{counter}" in existing:
            counter += 1
        return f"{base}_{counter}"

    def _show_context_menu(self, position: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)

        insert_row_above = menu.addAction("Insert Row Above")
        insert_row_below = menu.addAction("Insert Row Below")
        delete_rows = menu.addAction("Delete Row(s)")
        menu.addSeparator()
        insert_col_left = menu.addAction("Insert Column Left")
        insert_col_right = menu.addAction("Insert Column Right")
        delete_cols = menu.addAction("Delete Column(s)")

        insert_row_above.triggered.connect(self.insert_row_above)
        insert_row_below.triggered.connect(self.insert_row_below)
        delete_rows.triggered.connect(self.delete_rows)
        insert_col_left.triggered.connect(self.insert_col_left)
        insert_col_right.triggered.connect(self.insert_col_right)
        delete_cols.triggered.connect(self.delete_cols)

        selection = self._table_view.selectionModel().selectedIndexes()
        has_selection = bool(selection)
        delete_rows.setEnabled(has_selection)
        delete_cols.setEnabled(has_selection)

        menu.exec(self._table_view.viewport().mapToGlobal(position))

    def _show_row_header_menu(self, position: QtCore.QPoint) -> None:
        row = self._table_view.verticalHeader().logicalIndexAt(position)
        menu = QtWidgets.QMenu(self)
        insert_above = menu.addAction("Insert Row Above")
        insert_below = menu.addAction("Insert Row Below")
        delete_row = menu.addAction("Delete Row")
        insert_above.triggered.connect(lambda: self._insert_row_at(row))
        insert_below.triggered.connect(lambda: self._insert_row_at(row + 1))
        delete_row.triggered.connect(lambda: self._delete_row_at(row))
        delete_row.setEnabled(row >= 0)
        menu.exec(self._table_view.verticalHeader().mapToGlobal(position))

    def _show_col_header_menu(self, position: QtCore.QPoint) -> None:
        col = self._table_view.horizontalHeader().logicalIndexAt(position)
        menu = QtWidgets.QMenu(self)
        insert_left = menu.addAction("Insert Column Left")
        insert_right = menu.addAction("Insert Column Right")
        delete_col = menu.addAction("Delete Column")
        insert_left.triggered.connect(lambda: self._insert_col_at(col))
        insert_right.triggered.connect(lambda: self._insert_col_at(col + 1))
        delete_col.triggered.connect(lambda: self._delete_col_at(col))
        delete_col.setEnabled(col >= 0)
        menu.exec(self._table_view.horizontalHeader().mapToGlobal(position))

    def _insert_row_at(self, row: int) -> None:
        row = max(0, min(row, len(self._document.rows)))
        self._model.insertRows(row, 1)

    def _delete_row_at(self, row: int) -> None:
        if row < 0 or row >= len(self._document.rows):
            return
        self._model.removeRows(row, 1)

    def _insert_col_at(self, col: int) -> None:
        col = max(0, min(col, len(self._document.header)))
        self._model.insertColumns(col, 1)
        if col < len(self._document.header):
            self._document.header[col] = self._generate_column_name()
            self._model.headerDataChanged.emit(QtCore.Qt.Orientation.Horizontal, col, col)

    def _delete_col_at(self, col: int) -> None:
        if col < 0 or col >= len(self._document.header):
            return
        self._model.removeColumns(col, 1)

    def sync_from_code_view(self) -> bool:
        if self._stack.currentIndex() != 1:
            return True
        text = self._code_edit.toPlainText()
        try:
            parsed = self._parse_csv_text(text)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "CSV Parse Error", str(exc))
            return False
        if parsed is not None:
            self._document = parsed
            self._model.set_document(parsed)
            self._push_history()
            self._dirty = True
        return True

    def _grid_match(self, value: str, text: str, case_sensitive: bool) -> bool:
        if case_sensitive:
            return text in value
        return text.lower() in value.lower()

    def _iter_cells(self):
        rows = len(self._document.rows)
        cols = len(self._document.header)
        for row in range(rows):
            for col in range(cols):
                yield row, col

    def _cell_text(self, row: int, col: int) -> str:
        index = self._model.index(row, col)
        value = self._model.data(index, QtCore.Qt.ItemDataRole.DisplayRole)
        return "" if value is None else str(value)

    def _activate_grid_view(self) -> bool:
        if self._stack.currentIndex() == 1:
            if not self.sync_from_code_view():
                return False
            self._grid_button.setChecked(True)
        return True

    def select_cell(self, row: int, col: int) -> None:
        index = self._model.index(row, col)
        if not index.isValid():
            return
        if not self._activate_grid_view():
            return
        selection = self._table_view.selectionModel()
        selection.clearSelection()
        selection.setCurrentIndex(
            index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self._table_view.scrollTo(index)

    def find_next_in_grid(self, text: str, case_sensitive: bool) -> bool:
        if not text:
            return False
        if not self._activate_grid_view():
            return False
        rows = len(self._document.rows)
        cols = len(self._document.header)
        if rows == 0 or cols == 0:
            return False
        current = self._table_view.selectionModel().currentIndex()
        start = 0
        if current.isValid():
            start = current.row() * cols + current.column() + 1
        total = rows * cols
        for offset in range(total):
            idx = (start + offset) % total
            row = idx // cols
            col = idx % cols
            value = self._cell_text(row, col)
            if self._grid_match(value, text, case_sensitive):
                self.select_cell(row, col)
                return True
        return False

    def find_all_in_grid(self, text: str, case_sensitive: bool) -> List[tuple[int, int, str]]:
        if not text:
            return []
        if not self._activate_grid_view():
            return []
        results: List[tuple[int, int, str]] = []
        for row, col in self._iter_cells():
            value = self._cell_text(row, col)
            if self._grid_match(value, text, case_sensitive):
                results.append((row, col, value))
        return results

    def replace_current_in_grid(
        self, find_text: str, replace_text: str, case_sensitive: bool
    ) -> bool:
        if not find_text:
            return False
        if not self._activate_grid_view():
            return False
        current = self._table_view.selectionModel().currentIndex()
        if current.isValid():
            value = self._cell_text(current.row(), current.column())
            if self._grid_match(value, find_text, case_sensitive):
                self._model.setData(current, replace_text)
                return True
        if self.find_next_in_grid(find_text, case_sensitive):
            current = self._table_view.selectionModel().currentIndex()
            if current.isValid():
                self._model.setData(current, replace_text)
                return True
        return False

    def replace_all_in_grid(
        self, find_text: str, replace_text: str, case_sensitive: bool
    ) -> int:
        if not find_text:
            return 0
        if not self._activate_grid_view():
            return 0
        count = 0
        for row, col in self._iter_cells():
            value = self._cell_text(row, col)
            if self._grid_match(value, find_text, case_sensitive):
                index = self._model.index(row, col)
                self._model.setData(index, replace_text)
                count += 1
        return count


class FindPanel(QtWidgets.QWidget):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = parent
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QGridLayout()

        self._find_input = QtWidgets.QLineEdit(self)
        self._case_check = QtWidgets.QCheckBox("Case sensitive", self)
        find_label = QtWidgets.QLabel("Find:", self)

        self._find_next_btn = QtWidgets.QPushButton("Find Next", self)
        self._find_all_btn = QtWidgets.QPushButton("Find All", self)

        form.addWidget(find_label, 0, 0)
        form.addWidget(self._find_input, 0, 1, 1, 3)
        form.addWidget(self._case_check, 1, 1, 1, 3)
        form.addWidget(self._find_next_btn, 2, 0)
        form.addWidget(self._find_all_btn, 2, 1)

        self._results = QtWidgets.QListWidget(self)
        self._results.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)

        layout.addLayout(form)
        layout.addWidget(self._results)

        self._find_next_btn.clicked.connect(self._on_find_next)
        self._find_all_btn.clicked.connect(self._on_find_all)
        self._results.itemDoubleClicked.connect(self._on_result_activated)

    def focus_input(self) -> None:
        self._find_input.setFocus()
        self._find_input.selectAll()

    def _current_editor(self) -> Optional[EditorWidget]:
        return self._main_window._current_editor()

    def _on_find_next(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        found = editor.find_next_in_grid(self._find_input.text(), self._case_check.isChecked())
        if not found:
            QtWidgets.QMessageBox.information(self, "Find", "No more matches found.")

    def _on_find_all(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        self._results.clear()
        matches = editor.find_all_in_grid(self._find_input.text(), self._case_check.isChecked())
        for row, col, value in matches:
            preview = " ".join(value.split())
            preview = self._ellipsize(preview, 40)
            item = QtWidgets.QListWidgetItem(f"Row {row + 1}, Col {col + 1}: {preview}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, (row, col))
            self._results.addItem(item)
        if not matches:
            QtWidgets.QMessageBox.information(self, "Find All", "No matches found.")

    def _on_result_activated(self, item: QtWidgets.QListWidgetItem) -> None:
        editor = self._current_editor()
        if not editor:
            return
        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(data, tuple) and len(data) == 2:
            row, col = data
            editor.select_cell(row, col)

    def _ellipsize(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[:limit - 1]}…"


class CellDetailPanel(QtWidgets.QWidget):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = parent
        self._editor: Optional[EditorWidget] = None
        self._row: Optional[int] = None
        self._col: Optional[int] = None

        layout = QtWidgets.QVBoxLayout(self)
        self._title = QtWidgets.QLabel("No cell selected.")
        self._title.setStyleSheet("font-weight: bold;")
        self._value_edit = QtWidgets.QPlainTextEdit(self)
        self._value_edit.setPlaceholderText("Select a cell to view/edit its value.")
        self._apply_btn = QtWidgets.QPushButton("Apply", self)
        self._apply_btn.setEnabled(False)

        layout.addWidget(self._title)
        layout.addWidget(self._value_edit)
        layout.addWidget(self._apply_btn)

        self._apply_btn.clicked.connect(self._apply_changes)

    def update_cell(self, editor: EditorWidget, row: int, col: int, value: str) -> None:
        self._editor = editor
        self._row = row
        self._col = col
        self._title.setText(f"Row {row + 1}, Col {col + 1}")
        self._value_edit.setPlainText(value)
        self._apply_btn.setEnabled(True)

    def clear(self) -> None:
        self._editor = None
        self._row = None
        self._col = None
        self._title.setText("No cell selected.")
        self._value_edit.setPlainText("")
        self._apply_btn.setEnabled(False)

    def _apply_changes(self) -> None:
        if not self._editor or self._row is None or self._col is None:
            return
        index = self._editor._model.index(self._row, self._col)
        self._editor._model.setData(index, self._value_edit.toPlainText())


class MermaidPreviewWindow(QtWidgets.QMainWindow):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mermaid Preview")
        self.resize(900, 600)

        splitter = QtWidgets.QSplitter(self)
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        self._code_edit = QtWidgets.QPlainTextEdit(self)
        self._code_edit.setPlaceholderText("Paste Mermaid code here...")
        self._preview = QtWebEngineWidgets.QWebEngineView(self)

        splitter.addWidget(self._code_edit)
        splitter.addWidget(self._preview)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._code_edit.textChanged.connect(self._update_preview)
        self._update_preview()

    def _update_preview(self) -> None:
        raw = self._code_edit.toPlainText()
        lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
        cleaned = []
        for line in lines:
            if line.lower().startswith("mermaid version"):
                continue
            cleaned.append(line)
        code = "\n".join(cleaned).strip()
        if code:
            first = code.splitlines()[0].strip().lower()
            starters = (
                "graph ",
                "flowchart ",
                "sequencediagram",
                "classdiagram",
                "statediagram",
                "erdiagram",
                "journey",
                "gantt",
                "pie",
                "requirementdiagram",
                "gitgraph",
            )
            if not first.startswith(starters):
                code = f"graph TD\n{code}"
        payload = json.dumps(code)
        html = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 16px; }}
      .mermaid {{ font-size: 16px; }}
      #preview {{ overflow: auto; }}
    </style>
  </head>
  <body>
    <div id="preview">Loading...</div>
    <script>
      window.addEventListener("load", () => {{
        const code = {payload};
        mermaid.initialize({{ startOnLoad: false }});
        mermaid
          .render("graph", code)
          .then(({{svg}}) => {{
            document.getElementById("preview").innerHTML = svg;
          }})
          .catch((err) => {{
            const target = document.getElementById("preview");
            target.textContent = err && err.message ? err.message : String(err);
          }});
      }});
    </script>
  </body>
</html>"""
        self._preview.setHtml(html)

class ReplaceDialog(QtWidgets.QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = parent
        self.setWindowTitle("Replace")
        self.setModal(False)
        layout = QtWidgets.QGridLayout(self)

        self._find_input = QtWidgets.QLineEdit(self)
        self._replace_input = QtWidgets.QLineEdit(self)
        self._case_check = QtWidgets.QCheckBox("Case sensitive", self)

        find_label = QtWidgets.QLabel("Find:", self)
        replace_label = QtWidgets.QLabel("Replace:", self)

        self._find_next_btn = QtWidgets.QPushButton("Find Next", self)
        self._replace_btn = QtWidgets.QPushButton("Replace", self)
        self._replace_all_btn = QtWidgets.QPushButton("Replace All", self)
        self._close_btn = QtWidgets.QPushButton("Close", self)

        layout.addWidget(find_label, 0, 0)
        layout.addWidget(self._find_input, 0, 1, 1, 3)
        layout.addWidget(replace_label, 1, 0)
        layout.addWidget(self._replace_input, 1, 1, 1, 3)
        layout.addWidget(self._case_check, 2, 1, 1, 3)
        layout.addWidget(self._find_next_btn, 3, 0)
        layout.addWidget(self._replace_btn, 3, 1)
        layout.addWidget(self._replace_all_btn, 3, 2)
        layout.addWidget(self._close_btn, 3, 3)

        self._find_next_btn.clicked.connect(self._on_find_next)
        self._replace_btn.clicked.connect(self._on_replace)
        self._replace_all_btn.clicked.connect(self._on_replace_all)
        self._close_btn.clicked.connect(self.close)

    def _current_editor(self) -> Optional[EditorWidget]:
        return self._main_window._current_editor()

    def _on_find_next(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        found = editor.find_next_in_grid(self._find_input.text(), self._case_check.isChecked())
        if not found:
            QtWidgets.QMessageBox.information(self, "Find", "No more matches found.")

    def _on_replace(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        replaced = editor.replace_current_in_grid(
            self._find_input.text(), self._replace_input.text(), self._case_check.isChecked()
        )
        if not replaced:
            QtWidgets.QMessageBox.information(self, "Replace", "No match selected.")

    def _on_replace_all(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        count = editor.replace_all_in_grid(
            self._find_input.text(), self._replace_input.text(), self._case_check.isChecked()
        )
        QtWidgets.QMessageBox.information(self, "Replace All", f"Replaced {count} match(es).")


class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self._search_text = ""
        self._extensions = {".csv", ".tsv"}

    def set_search_text(self, text: str) -> None:
        self._search_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if not index.isValid():
            return False
        path = model.filePath(index)
        if model.isDir(index):
            return True
        _, ext = os.path.splitext(path)
        if ext.lower() not in self._extensions:
            return False
        if not self._search_text:
            return True
        return self._search_text in os.path.basename(path).lower()


class GraphView(QtWidgets.QGraphicsView):
    node_activated = QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setInteractive(True)
        self._min_scale = 0.2
        self._max_scale = 4.0
        self.grabGesture(QtCore.Qt.GestureType.PinchGesture)

    def _apply_scale(self, factor: float) -> None:
        if factor == 1.0:
            return
        current = self.transform().m11()
        target = current * factor
        if target < self._min_scale:
            factor = self._min_scale / current
        elif target > self._max_scale:
            factor = self._max_scale / current
        if factor != 1.0:
            self.scale(factor, factor)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        angle = event.angleDelta().y()
        pixel = event.pixelDelta().y()
        if angle == 0 and pixel == 0:
            super().wheelEvent(event)
            return
        if angle != 0:
            steps = angle / 120.0
            factor = 1.15 ** steps
        else:
            factor = 1.0 + (pixel / 600.0)
            if factor <= 0:
                return
        self._apply_scale(factor)
        event.accept()

    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.Type.Gesture:
            return self._on_gesture(event)
        return super().event(event)

    def _on_gesture(self, event: QtCore.QEvent) -> bool:
        gesture = event.gesture(QtCore.Qt.GestureType.PinchGesture)
        if isinstance(gesture, QtWidgets.QPinchGesture):
            self._apply_scale(gesture.scaleFactor())
            return True
        return False

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self.scene().itemAt(scene_pos, QtGui.QTransform())
        if isinstance(item, QtWidgets.QGraphicsEllipseItem):
            path = item.data(0)
            if isinstance(path, str):
                self.node_activated.emit(path)
        super().mouseDoubleClickEvent(event)


class RelationPanel(QtWidgets.QWidget):
    file_activated = QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._root_path = QtCore.QDir.currentPath()
        self._edge_items: List[QtWidgets.QGraphicsLineItem] = []
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(300)
        layout = QtWidgets.QVBoxLayout(self)
        header_layout = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Relationship Graph")
        title.setStyleSheet("font-weight: bold;")
        self._auto_check = QtWidgets.QCheckBox("Auto", self)
        self._debug_check = QtWidgets.QCheckBox("Debug", self)
        self._scan_button = QtWidgets.QToolButton(self)
        self._scan_button.setText("Scan")
        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setVisible(False)
        self._progress.setMinimumWidth(140)
        self._progress.setTextVisible(True)
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(self._auto_check)
        header_layout.addWidget(self._debug_check)
        header_layout.addWidget(self._progress)
        header_layout.addWidget(self._scan_button)
        self._view = GraphView(self)
        self._scene = QtWidgets.QGraphicsScene(self)
        self._view.setScene(self._scene)
        self._view.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self._detail_label = QtWidgets.QLabel("Select an edge to view shared fields.")
        self._detail_label.setWordWrap(True)
        layout.addLayout(header_layout)
        layout.addWidget(self._view)
        layout.addWidget(self._detail_label)

        self._scan_button.clicked.connect(self.refresh_graph)
        self._auto_check.toggled.connect(self._on_auto_toggled)
        self._debug_check.toggled.connect(self.refresh_graph)
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._view.node_activated.connect(self.file_activated.emit)
        self._watcher.directoryChanged.connect(self._on_directory_changed)
        self._refresh_timer.timeout.connect(self._refresh_if_auto)

    def set_root_path(self, path: str) -> None:
        self._root_path = path
        self._update_watch_paths()
        if self._auto_check.isChecked():
            self.refresh_graph()

    def refresh_graph(self) -> None:
        self._scene.clear()
        self._edge_items = []
        if self._debug_check.isChecked():
            self._render_debug_graph()
            self._detail_label.setText("Debug graph rendered.")
            return
        self._detail_label.setText(f"Scanning: {self._root_path}")
        files = self._scan_csv_files(self._root_path)
        if not files:
            text_item = self._scene.addText("No CSV/TSV files found.")
            self._scene.setSceneRect(text_item.boundingRect().adjusted(-40, -40, 40, 40))
            self._detail_label.setText(f"No CSV/TSV files found in: {self._root_path}")
            self._progress.setVisible(False)
            return
        self._progress.setVisible(False)
        edges = self._build_edges(files)
        if not edges:
            text_item = self._scene.addText("No related files found.")
            self._scene.setSceneRect(text_item.boundingRect().adjusted(-40, -40, 40, 40))
            self._detail_label.setText("No related files found.")
            return
        related = sorted({path for left, right, _ in edges for path in (left, right)})
        self._render_graph(related, edges)
        self._detail_label.setText(
            f"Found {len(files)} file(s) with {len(edges)} name-similarity link(s)."
        )
        self._progress.setVisible(False)

    def _scan_csv_files(self, root_path: str) -> List[str]:
        result = []
        for entry in os.scandir(root_path):
            if entry.is_file():
                _, ext = os.path.splitext(entry.name)
                if ext.lower() in {".csv", ".tsv"}:
                    result.append(entry.path)
        return result

    def _build_edges(self, paths: List[str]) -> List[tuple[str, str, List[str]]]:
        edges: List[tuple[str, str, List[str]]] = []
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                left = paths[i]
                right = paths[j]
                shared = self._common_prefix_tokens(left, right)
                if shared:
                    edges.append((left, right, shared))
        return edges

    def _render_graph(self, files: List[str], edges: List[tuple[str, str, List[str]]]) -> None:
        x_spacing = 140
        y_spacing = 80
        center = QtCore.QPointF(0, 0)
        node_items: dict[str, QtWidgets.QGraphicsEllipseItem] = {}
        text_items: dict[str, QtWidgets.QGraphicsTextItem] = {}

        groups = self._group_by_relationships(files, edges)
        y_cursor = center.y()
        for group in groups:
            for idx, path in enumerate(group):
                x = center.x() + x_spacing * idx
                y = y_cursor
                node = QtWidgets.QGraphicsEllipseItem(-4, -4, 8, 8)
                node.setBrush(QtGui.QColor("#4A7EBB"))
                node.setPen(QtGui.QPen(QtGui.QColor("#4A7EBB"), 1.0))
                node.setPos(x, y)
                node.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                node.setData(0, path)
                label = os.path.splitext(os.path.basename(path))[0]
                text = QtWidgets.QGraphicsTextItem(label)
                text.setDefaultTextColor(QtGui.QColor("#2B3A42"))
                text.setPos(x - text.boundingRect().width() / 2, y - 22)
                node_items[path] = node
                text_items[path] = text
                self._scene.addItem(node)
                self._scene.addItem(text)
            y_cursor += y_spacing

        for left, right, shared in edges:
            left_item = node_items.get(left)
            right_item = node_items.get(right)
            if not left_item or not right_item:
                continue
            line = QtWidgets.QGraphicsLineItem(QtCore.QLineF(left_item.pos(), right_item.pos()))
            pen = QtGui.QPen(QtGui.QColor("#7A8794"), 1.2)
            line.setPen(pen)
            tooltip = ", ".join(shared)
            line.setToolTip(tooltip)
            line.setData(0, tooltip)
            line.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            self._scene.addItem(line)
            self._edge_items.append(line)

        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-80, -80, 80, 80))
        self._view.resetTransform()
        self._view.fitInView(
            self._scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio
        )

    def _render_debug_graph(self) -> None:
        files = ["debug_left.csv", "debug_right.csv"]
        edges = [(files[0], files[1], ["debug"])]
        self._render_graph(files, edges)

    def _group_by_relationships(
        self, files: List[str], edges: List[tuple[str, str, List[str]]]
    ) -> List[List[str]]:
        parent = {path: path for path in files}

        def find(path: str) -> str:
            while parent[path] != path:
                parent[path] = parent[parent[path]]
                path = parent[path]
            return path

        def union(a: str, b: str) -> None:
            root_a = find(a)
            root_b = find(b)
            if root_a != root_b:
                parent[root_b] = root_a

        for left, right, _ in edges:
            union(left, right)

        groups: dict[str, List[str]] = {}
        for path in files:
            root = find(path)
            groups.setdefault(root, []).append(path)

        ordered_groups = [sorted(group) for group in groups.values()]
        ordered_groups.sort(key=lambda group: os.path.basename(group[0]).lower())
        return ordered_groups

    def _common_prefix_tokens(self, left: str, right: str) -> List[str]:
        left_name = self._normalize_name(left)
        right_name = self._normalize_name(right)
        prefix = os.path.commonprefix([left_name, right_name]).strip("_")
        if len(prefix) < 2:
            return []
        return [prefix]

    def _normalize_name(self, path: str) -> str:
        name = os.path.splitext(os.path.basename(path))[0].lower()
        normalized = []
        prev_underscore = False
        for ch in name:
            if ch.isalnum():
                normalized.append(ch)
                prev_underscore = False
            else:
                if not prev_underscore:
                    normalized.append("_")
                    prev_underscore = True
        return "".join(normalized).strip("_")

    def _on_selection_changed(self) -> None:
        default_pen = QtGui.QPen(QtGui.QColor("#7A8794"), 1.2)
        highlight_pen = QtGui.QPen(QtGui.QColor("#2F6FDB"), 2.2)
        selected_fields = ""
        for line in self._edge_items:
            line.setPen(default_pen)
        for item in self._scene.selectedItems():
            if isinstance(item, QtWidgets.QGraphicsLineItem):
                item.setPen(highlight_pen)
                fields = item.data(0)
                if isinstance(fields, str):
                    selected_fields = fields
        if selected_fields:
            self._detail_label.setText(f"Shared fields: {selected_fields}")
        else:
            self._detail_label.setText("Select an edge to view shared fields.")

    def _on_auto_toggled(self, checked: bool) -> None:
        self._scan_button.setEnabled(not checked)
        if checked:
            self.refresh_graph()

    def _on_directory_changed(self, _: str) -> None:
        if self._auto_check.isChecked():
            self._refresh_timer.start()

    def _refresh_if_auto(self) -> None:
        if self._auto_check.isChecked():
            self._update_watch_paths()
            self.refresh_graph()

    def _update_watch_paths(self) -> None:
        current = set(self._watcher.directories())
        target = set()
        if self._root_path:
            for root, dirs, _ in os.walk(self._root_path):
                target.add(root)
                for name in dirs:
                    target.add(os.path.join(root, name))
        remove = list(current - target)
        add = list(target - current)
        if remove:
            self._watcher.removePaths(remove)
        if add:
            self._watcher.addPaths(add)



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CSV-IDE Prototype")
        self.resize(1200, 720)
        self._settings = QtCore.QSettings("CSV-IDE", "CSV-IDE")

        splitter = QtWidgets.QSplitter(self)
        splitter.setOrientation(QtCore.Qt.Orientation.Horizontal)

        left_panel = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        self._search_input = QtWidgets.QLineEdit(self)
        self._search_input.setPlaceholderText("Filter files...")
        self._file_list = QtWidgets.QListWidget(self)
        self._file_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self._file_list.itemSelectionChanged.connect(self._on_file_selection_changed)
        self._file_list.itemDoubleClicked.connect(self._open_from_list)
        self._search_input.textChanged.connect(self._filter_file_list)
        left_layout.addWidget(self._search_input)
        left_layout.addWidget(self._file_list)

        self._tabs = QtWidgets.QTabWidget(self)
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(False)
        self._tabs.tabCloseRequested.connect(lambda _: self.close_current_tab())

        right_panel = QtWidgets.QTabWidget(self)
        relation_panel = RelationPanel(self)
        relation_panel.set_root_path(QtCore.QDir.currentPath())
        relation_panel.file_activated.connect(self.open_file)
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
        self._relation_panel = relation_panel
        self._right_tabs = right_panel
        self._current_path: Optional[str] = None
        self._ignore_selection_change = False
        self._replace_dialog: Optional[ReplaceDialog] = None
        self._mermaid_preview_window: Optional[MermaidPreviewWindow] = None
        self._build_actions()
        self._root_path = self._settings.value("last_root_path", self._root_path, type=str)
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
        if self._current_path and self._current_path != path:
            current = self._open_documents.get(self._current_path)
            if current and current.is_dirty():
                if not self._confirm_discard(current):
                    self._ignore_selection_change = True
                    self._select_path(self._current_path)
                    self._ignore_selection_change = False
                    return
        self.open_file(path)
        self._persist_session_state()

    def open_file(self, path: str) -> None:
        if path in self._open_documents:
            widget = self._open_documents[path]
            self._show_single_tab(widget)
            self._current_path = path
            self._update_window_title(widget)
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

        self._show_single_tab(editor)
        self._current_path = path
        self._update_status(editor)
        self._update_window_title(editor)
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
        mermaid_preview_action = QtGui.QAction("Mermaid Preview...", self)
        mermaid_preview_action.triggered.connect(self.open_mermaid_preview)
        tools_menu.addAction(mermaid_preview_action)

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
            mermaid_preview_action,
        ):
            action.setShortcutContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
            self.addAction(action)

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
        self._show_single_tab(editor)
        self._current_path = path
        self._update_status(editor)
        self._update_window_title(editor)
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

    def open_mermaid_preview(self) -> None:
        if self._mermaid_preview_window is None:
            self._mermaid_preview_window = MermaidPreviewWindow(self)
        self._mermaid_preview_window.show()
        self._mermaid_preview_window.raise_()
        self._mermaid_preview_window.activateWindow()

    def open_folder(self, path: str) -> None:
        self._root_path = path
        self._settings.setValue("last_root_path", path)
        self._relation_panel.set_root_path(path)
        self._populate_file_list(path)
        for root, _, files in os.walk(path):
            for name in files:
                _, ext = os.path.splitext(name)
                if ext.lower() in {".csv", ".tsv"}:
                    self.open_file(os.path.join(root, name))

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
        editor.document.path = new_path
        self._open_documents.pop(current_path, None)
        self._open_documents[new_path] = editor
        self._update_window_title(editor)
        self._update_list_item_path(current_path, new_path)
        self._status_bar.showMessage(f"Renamed to: {os.path.basename(new_path)}")

    def close_current_tab(self) -> None:
        editor = self._current_editor()
        if not editor:
            return
        if editor.is_dirty():
            if not self._confirm_discard(editor):
                return
        path = editor.document.path
        self._open_documents.pop(path, None)
        self._tabs.clear()
        editor.deleteLater()
        self._current_path = None
        self._update_window_title(None)
        self._persist_session_state()
        self._cell_panel.clear()

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
            self.setWindowTitle("CSV-IDE Prototype")
            return
        name = os.path.basename(editor.document.path)
        if editor.is_dirty():
            name = f"*{name}"
        self.setWindowTitle(f"{name} - CSV-IDE")
        self._update_tab_label(editor)

    def _update_tab_label(self, editor: EditorWidget) -> None:
        if self._tabs.count() == 0:
            return
        label = os.path.basename(editor.document.path)
        if editor.is_dirty():
            label = f"*{label}"
        self._tabs.setTabText(0, label)

    def _show_single_tab(self, editor: EditorWidget) -> None:
        self._tabs.blockSignals(True)
        self._tabs.clear()
        label = os.path.basename(editor.document.path)
        if editor.is_dirty():
            label = f"*{label}"
        self._tabs.addTab(editor, label)
        self._tabs.setCurrentWidget(editor)
        self._tabs.blockSignals(False)
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
            item.setToolTip(full_path)
            self._file_list.addItem(item)

    def _filter_file_list(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            name = item.text().lower()
            item.setHidden(bool(text) and text not in name)

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
                item.setToolTip(new_path)
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


def main() -> None:
    def _log_unhandled(exc_type, exc_value, exc_traceback) -> None:
        traceback.print_exception(exc_type, exc_value, exc_traceback)

    sys.excepthook = _log_unhandled
    faulthandler.enable()

    def _log_sigterm(signum, frame) -> None:
        print(f"Received signal {signum}, dumping stack.")
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)

    signal.signal(signal.SIGTERM, _log_sigterm)
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()
    QtCore.QTimer.singleShot(0, window.activateWindow)
    app.exec()


if __name__ == "__main__":
    main()
