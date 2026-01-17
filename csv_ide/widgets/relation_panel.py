from typing import List, Optional

from PyQt6 import QtCore, QtWidgets

from csv_ide.widgets.html_preview import HtmlPreviewWindow


class RelationPanel(QtWidgets.QWidget):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._preview_windows: List[HtmlPreviewWindow] = []
        self._settings = QtCore.QSettings("CSV-IDE", "CSV-IDE")
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Relationship Graph")
        title.setStyleSheet("font-weight: bold;")
        help_label = QtWidgets.QLabel(
            "Paste HTML or Mermaid-style graph text, then click Apply to render."
        )
        help_label.setWordWrap(True)
        self._input = QtWidgets.QPlainTextEdit(self)
        self._input.setPlaceholderText("Paste HTML or graph text here...")
        self._apply_button = QtWidgets.QPushButton("Apply", self)
        self._apply_button.clicked.connect(self._open_preview)

        layout.addWidget(title)
        layout.addWidget(help_label)
        layout.addWidget(self._input)
        layout.addWidget(self._apply_button)

        last_value = self._settings.value("relation_panel_last_html", "", type=str)
        if last_value:
            self._input.setPlainText(last_value)
        self._input.textChanged.connect(self._persist_input)

    def _persist_input(self) -> None:
        self._settings.setValue("relation_panel_last_html", self._input.toPlainText())

    def _open_preview(self) -> None:
        content = self._input.toPlainText()
        window = HtmlPreviewWindow(self, show_editor=False)
        window.set_content(content)
        window.show()
        window.raise_()
        window.activateWindow()
        self._preview_windows.append(window)
        window.destroyed.connect(self._cleanup_windows)

    def _cleanup_windows(self, *_: object) -> None:
        alive: List[HtmlPreviewWindow] = []
        for window in self._preview_windows:
            try:
                if window.isVisible():
                    alive.append(window)
            except RuntimeError:
                continue
        self._preview_windows = alive
