from typing import Optional, TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

from csv_ide.widgets.editor import EditorWidget

if TYPE_CHECKING:
    from csv_ide.windows.main_window import MainWindow


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
