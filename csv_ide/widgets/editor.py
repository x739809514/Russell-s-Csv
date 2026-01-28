import csv
import io
from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from csv_ide.models import CsvDocument, CSVTableModel


class ConflictHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent: QtGui.QTextDocument) -> None:
        super().__init__(parent)
        self._marker_format = QtGui.QTextCharFormat()
        self._marker_format.setForeground(QtGui.QColor("#b00020"))
        self._marker_format.setBackground(QtGui.QColor("#ffe8e8"))
        self._ours_format = QtGui.QTextCharFormat()
        self._ours_format.setBackground(QtGui.QColor("#fff6d6"))
        self._theirs_format = QtGui.QTextCharFormat()
        self._theirs_format.setBackground(QtGui.QColor("#e6f6ff"))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt override
        state = self.previousBlockState()
        if text.startswith("<<<<<<<"):
            self.setFormat(0, len(text), self._marker_format)
            self.setCurrentBlockState(1)
            return
        if text.startswith("======="):
            self.setFormat(0, len(text), self._marker_format)
            self.setCurrentBlockState(2)
            return
        if text.startswith(">>>>>>>"):
            self.setFormat(0, len(text), self._marker_format)
            self.setCurrentBlockState(0)
            return
        if state == 1:
            self.setFormat(0, len(text), self._ours_format)
            self.setCurrentBlockState(1)
        elif state == 2:
            self.setFormat(0, len(text), self._theirs_format)
            self.setCurrentBlockState(2)
        else:
            self.setCurrentBlockState(0)


class EditorWidget(QtWidgets.QWidget):
    document_changed = QtCore.pyqtSignal(str)
    cell_selected = QtCore.pyqtSignal(int, int, str)
    table_state_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        document: CsvDocument,
        parent: Optional[QtWidgets.QWidget] = None,
        raw_text: Optional[str] = None,
        parse_error: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._undo_stack: List[CsvDocument] = []
        self._undo_index = -1
        self._ignore_history = False
        self._dirty = False
        self._parse_error: Optional[str] = None
        self._code_source_text: Optional[str] = None
        self._custom_row_heights: dict[int, int] = {}

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
        self._table_view.setWordWrap(True)
        self._table_view.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self._table_view.horizontalHeader().setStretchLastSection(True)
        self._table_view.verticalHeader().setVisible(True)
        self._table_view.installEventFilter(self)
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
        self._table_view.verticalHeader().sectionResized.connect(self._on_row_resized)
        self._table_view.horizontalHeader().customContextMenuRequested.connect(
            self._show_col_header_menu
        )
        self._table_view.horizontalHeader().sectionDoubleClicked.connect(self._rename_column_at)
        self._table_view.horizontalHeader().sectionResized.connect(self._on_column_resized)
        self._grid_stack = QtWidgets.QStackedWidget(self)
        self._grid_error_label = QtWidgets.QLabel(self)
        self._grid_error_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._grid_error_label.setWordWrap(True)
        self._grid_stack.addWidget(self._table_view)
        self._grid_stack.addWidget(self._grid_error_label)
        self._stack.addWidget(self._grid_stack)

        self._code_edit = QtWidgets.QPlainTextEdit(self)
        self._code_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._conflict_highlighter = ConflictHighlighter(self._code_edit.document())
        self._stack.addWidget(self._code_edit)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(toggle_layout)
        layout.addWidget(self._stack)

        self._model = CSVTableModel(self._document, self)
        self._table_view.setModel(self._model)
        self._table_view.selectionModel().currentChanged.connect(self._on_current_cell_changed)
        self._table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)

        self._toggle_group.buttonToggled.connect(self._on_toggle)
        self._code_edit.textChanged.connect(self._on_code_changed)
        self._model.dataChanged.connect(self._on_model_changed)
        self._model.rowsInserted.connect(lambda *_: self._on_model_changed())
        self._model.rowsRemoved.connect(lambda *_: self._on_model_changed())
        self._model.columnsInserted.connect(lambda *_: self._on_model_changed())
        self._model.columnsRemoved.connect(lambda *_: self._on_model_changed())
        self._push_history()

        if raw_text is not None:
            self._code_source_text = raw_text
            self._code_edit.setPlainText(raw_text)
        if parse_error:
            self._set_parse_error(parse_error)
            self._code_button.setChecked(True)
            self._stack.setCurrentIndex(1)
        else:
            self._set_parse_error(None)

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
        self._code_source_text = None
        self._set_parse_error(None)
        if self._stack.currentIndex() == 1:
            self._code_edit.setPlainText(self._serialize_document())

    def show_parse_error(self, raw_text: str, message: str) -> None:
        self._code_source_text = raw_text
        self._code_edit.blockSignals(True)
        self._code_edit.setPlainText(raw_text)
        self._code_edit.blockSignals(False)
        self._set_parse_error(message)
        self._code_button.setChecked(True)
        self._stack.setCurrentIndex(1)
        self._dirty = False

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

    def _set_parse_error(self, message: Optional[str]) -> None:
        self._parse_error = message
        if message:
            self._grid_error_label.setText(
                "CSV parse error. Check the Code view for details.\n\n" + message
            )
            self._grid_stack.setCurrentWidget(self._grid_error_label)
        else:
            self._grid_stack.setCurrentWidget(self._table_view)

    def _on_toggle(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if not checked:
            return
        if button is self._code_button:
            self._code_edit.blockSignals(True)
            if self._parse_error and self._code_source_text is not None:
                self._code_edit.setPlainText(self._code_source_text)
            else:
                self._code_edit.setPlainText(self._serialize_document())
            self._code_edit.blockSignals(False)
            self._stack.setCurrentIndex(1)
        else:
            text = self._code_edit.toPlainText()
            try:
                parsed = self._parse_csv_text(text)
            except ValueError as exc:
                self._code_source_text = text
                self._set_parse_error(str(exc))
                self._stack.setCurrentIndex(0)
                return
            if parsed is not None:
                self._document = parsed
                self._model.set_document(parsed)
                self._push_history()
                self.document_changed.emit(parsed.path)
            self._code_source_text = None
            self._set_parse_error(None)
            self._stack.setCurrentIndex(0)

    def _on_code_changed(self) -> None:
        if self._stack.currentIndex() == 1:
            if self._parse_error is not None:
                self._code_source_text = self._code_edit.toPlainText()
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
            self._resize_row_to_contents(current.row())

    def _on_current_cell_changed(
        self, current: QtCore.QModelIndex, _: QtCore.QModelIndex
    ) -> None:
        if current.isValid():
            self._emit_cell_selected(current.row(), current.column())
            self._resize_row_to_contents(current.row())

    def _emit_cell_selected(self, row: int, col: int) -> None:
        value = self._cell_text(row, col)
        self.cell_selected.emit(row, col, value)

    def _on_selection_changed(self, *_: object) -> None:
        if not (QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.AltModifier):
            return
        selection = self._table_view.selectionModel().selectedIndexes()
        if len(selection) < 2:
            return
        cols = {index.column() for index in selection}
        if len(cols) != 1:
            return
        current = self._table_view.selectionModel().currentIndex()
        if not current.isValid():
            return
        col = current.column()
        if col not in cols:
            return
        anchor_row = current.row()
        anchor_value = self._cell_text(anchor_row, col)
        match = re.match(r"^(.*?)(-?\\d+)([^\\d]*)$", anchor_value)
        if not match:
            return
        prefix, number_text, suffix = match.groups()
        base = int(number_text)
        for index in selection:
            row = index.row()
            new_value = f"{prefix}{base + (row - anchor_row)}{suffix}"
            self._model.setData(index, new_value)

    def _on_column_resized(self, *_: object) -> None:
        self._resize_current_row_height()
        self.table_state_changed.emit()

    def _on_row_resized(self, row: int, _: int, new_size: int) -> None:
        default_height = self._table_view.verticalHeader().defaultSectionSize()
        if new_size == default_height:
            self._custom_row_heights.pop(row, None)
        else:
            self._custom_row_heights[row] = new_size
        self.table_state_changed.emit()

    def _resize_current_row_height(self) -> None:
        current = self._table_view.selectionModel().currentIndex()
        if current.isValid():
            self._resize_row_to_contents(current.row())

    def _resize_row_to_contents(self, row: int) -> None:
        if row < 0:
            return
        font = self._table_view.font()
        default_height = self._table_view.verticalHeader().defaultSectionSize()
        max_height = default_height
        padding = 6
        col_count = self._model.columnCount()
        for col in range(col_count):
            index = self._model.index(row, col)
            text = self._model.data(index, QtCore.Qt.ItemDataRole.DisplayRole)
            if text is None:
                text = ""
            width = max(self._table_view.columnWidth(col) - padding * 2, 1)
            doc = QtGui.QTextDocument()
            doc.setDefaultFont(font)
            doc.setPlainText(str(text))
            doc.setTextWidth(width)
            height = int(doc.size().height()) + padding * 2
            if height > max_height:
                max_height = height
        if self._table_view.rowHeight(row) != max_height:
            self._table_view.setRowHeight(row, max_height)
            if max_height == default_height:
                self._custom_row_heights.pop(row, None)
            else:
                self._custom_row_heights[row] = max_height
            self.table_state_changed.emit()

    def table_state(self) -> dict:
        col_count = self._model.columnCount()
        columns = [self._table_view.columnWidth(col) for col in range(col_count)]
        rows = [[row, height] for row, height in sorted(self._custom_row_heights.items())]
        return {"columns": columns, "rows": rows}

    def apply_table_state(self, state: dict) -> None:
        if not state:
            return
        columns = state.get("columns")
        if isinstance(columns, list):
            col_count = self._model.columnCount()
            for col, width in enumerate(columns):
                if col >= col_count:
                    break
                if isinstance(width, int) and width > 0:
                    self._table_view.setColumnWidth(col, width)
        rows = state.get("rows")
        if isinstance(rows, list):
            row_count = self._model.rowCount()
            for item in rows:
                if (
                    isinstance(item, (list, tuple))
                    and len(item) == 2
                    and isinstance(item[0], int)
                    and isinstance(item[1], int)
                ):
                    row, height = item
                    if 0 <= row < row_count and height > 0:
                        self._table_view.setRowHeight(row, height)
                        self._custom_row_heights[row] = height

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

    def _clear_selected_cells(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        targets = selection or [self._table_view.selectionModel().currentIndex()]
        for index in targets:
            if index.isValid():
                self._model.setData(index, "")

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self._table_view and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.matches(QtGui.QKeySequence.StandardKey.Copy):
                self._copy_selection_to_clipboard()
                return True
            if event.matches(QtGui.QKeySequence.StandardKey.Paste):
                self._paste_from_clipboard()
                return True
            if event.key() in (QtCore.Qt.Key.Key_Delete, QtCore.Qt.Key.Key_Backspace):
                self._clear_selected_cells()
                return True
        return super().eventFilter(obj, event)

    def _copy_selection_to_clipboard(self) -> None:
        selection = self._table_view.selectionModel().selectedIndexes()
        if not selection:
            current = self._table_view.selectionModel().currentIndex()
            if current.isValid():
                selection = [current]
            else:
                return
        rows = sorted({index.row() for index in selection})
        cols = sorted({index.column() for index in selection})
        min_row, max_row = rows[0], rows[-1]
        min_col, max_col = cols[0], cols[-1]
        row_count = max_row - min_row + 1
        col_count = max_col - min_col + 1
        grid = [[""] * col_count for _ in range(row_count)]
        for index in selection:
            r = index.row() - min_row
            c = index.column() - min_col
            value = self._model.data(index, QtCore.Qt.ItemDataRole.DisplayRole)
            grid[r][c] = "" if value is None else str(value)
        text = "\n".join("\t".join(row) for row in grid)
        QtWidgets.QApplication.clipboard().setText(text)

    def _paste_from_clipboard(self) -> None:
        current = self._table_view.selectionModel().currentIndex()
        if not current.isValid():
            return
        text = QtWidgets.QApplication.clipboard().text()
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        reader = csv.reader(io.StringIO(text), delimiter="\t")
        rows = [row for row in reader]
        while rows and all(cell == "" for cell in rows[-1]):
            rows.pop()
        if not rows:
            return
        start_row = current.row()
        start_col = current.column()
        max_cols = self._model.columnCount()
        if start_col >= max_cols:
            return
        needed_rows = start_row + len(rows) - self._model.rowCount()
        if needed_rows > 0:
            self._model.insertRows(self._model.rowCount(), needed_rows)
        for r, row in enumerate(rows):
            if not row:
                continue
            row = row[: max_cols - start_col]
            for c, value in enumerate(row):
                index = self._model.index(start_row + r, start_col + c)
                if index.isValid():
                    self._model.setData(index, value)
        self._resize_row_to_contents(start_row)

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
        rename_col = menu.addAction("Rename Column")
        delete_col = menu.addAction("Delete Column")
        insert_left.triggered.connect(lambda: self._insert_col_at(col))
        insert_right.triggered.connect(lambda: self._insert_col_at(col + 1))
        rename_col.triggered.connect(lambda: self._rename_column_at(col))
        delete_col.triggered.connect(lambda: self._delete_col_at(col))
        rename_col.setEnabled(col >= 0)
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

    def _rename_column_at(self, col: int) -> None:
        if col < 0 or col >= len(self._document.header):
            return
        current = self._document.header[col] if col < len(self._document.header) else ""
        new_name, ok = QtWidgets.QInputDialog.getText(
            self, "Rename Column", "Column name:", text=current
        )
        if not ok:
            return
        if self._model.setHeaderData(col, QtCore.Qt.Orientation.Horizontal, new_name):
            self._on_model_changed()

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
