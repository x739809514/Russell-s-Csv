from typing import Optional, TYPE_CHECKING

from PyQt6 import QtWidgets

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
