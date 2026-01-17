from typing import Optional, TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

from csv_ide.widgets.editor import EditorWidget

if TYPE_CHECKING:
    from csv_ide.windows.main_window import MainWindow


class CellDetailPanel(QtWidgets.QWidget):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = parent
        self._editor: Optional[EditorWidget] = None
        self._row: Optional[int] = None
        self._col: Optional[int] = None
        self._selected_cells: list[tuple[int, int]] = []

        layout = QtWidgets.QVBoxLayout(self)
        self._title = QtWidgets.QLabel("No cell selected.")
        self._title.setStyleSheet("font-weight: bold;")
        self._value_edit = QtWidgets.QPlainTextEdit(self)
        self._value_edit.setPlaceholderText("Select a cell to view/edit its value.")
        self._value_edit.installEventFilter(self)
        self._increment_check = QtWidgets.QCheckBox("Increment", self)
        self._apply_btn = QtWidgets.QPushButton("Apply", self)
        self._apply_btn.setEnabled(False)

        layout.addWidget(self._title)
        layout.addWidget(self._value_edit)
        layout.addWidget(self._increment_check)
        layout.addWidget(self._apply_btn)

        self._apply_btn.clicked.connect(self._apply_changes)

    def update_cell(self, editor: EditorWidget, row: int, col: int, value: str) -> None:
        self._editor = editor
        self._row = row
        self._col = col
        selected = editor._table_view.selectionModel().selectedIndexes()
        if selected:
            self._selected_cells = [(index.row(), index.column()) for index in selected]
        else:
            self._selected_cells = []
        if len(selected) > 1:
            self._title.setText(f"{len(selected)} cells selected")
        else:
            self._title.setText(f"Row {row + 1}, Col {col + 1}")
        self._value_edit.setPlainText(value)
        self._apply_btn.setEnabled(True)

    def clear(self) -> None:
        self._editor = None
        self._row = None
        self._col = None
        self._selected_cells = []
        self._title.setText("No cell selected.")
        self._value_edit.setPlainText("")
        self._increment_check.setChecked(False)
        self._apply_btn.setEnabled(False)

    def _apply_changes(self) -> None:
        if not self._editor or self._row is None or self._col is None:
            return
        selection = self._editor._table_view.selectionModel().selectedIndexes()
        if selection:
            targets = selection
        elif self._selected_cells:
            targets = [
                self._editor._model.index(row, col) for row, col in self._selected_cells
            ]
        else:
            targets = [self._editor._model.index(self._row, self._col)]
        if self._increment_check.isChecked() and targets:
            ordered = sorted(targets, key=lambda idx: (idx.row(), idx.column()))
            first = ordered[0]
            base_text = self._editor._model.data(first, QtCore.Qt.ItemDataRole.DisplayRole)
            if base_text is None:
                return
            base_text = str(base_text).strip()
            if not base_text.isdigit():
                return
            base = int(base_text)
            for offset, index in enumerate(ordered):
                if index.isValid():
                    self._editor._model.setData(index, str(base + offset))
            return
        new_value = self._value_edit.toPlainText()
        for index in targets:
            if index.isValid():
                self._editor._model.setData(index, new_value)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj is self._value_edit and event.type() == QtCore.QEvent.Type.KeyPress:
            if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                if not (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier):
                    self._apply_changes()
                    return True
        return super().eventFilter(obj, event)
