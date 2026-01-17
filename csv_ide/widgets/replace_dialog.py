from typing import Optional, TYPE_CHECKING

from PyQt6 import QtWidgets

from csv_ide.widgets.editor import EditorWidget

if TYPE_CHECKING:
    from csv_ide.windows.main_window import MainWindow


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
