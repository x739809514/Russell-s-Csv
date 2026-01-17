from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from csv_ide.windows.main_window import MainWindow


class RelationEditorDialog(QtWidgets.QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = parent
        self.setWindowTitle("Relation Editor")
        self.setModal(False)

        layout = QtWidgets.QVBoxLayout(self)

        self._current_label = QtWidgets.QLabel(self)
        self._current_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._current_label)

        form = QtWidgets.QGridLayout()
        self._from_field = QtWidgets.QComboBox(self)
        self._to_table = QtWidgets.QComboBox(self)
        self._to_field = QtWidgets.QComboBox(self)
        self._type_combo = QtWidgets.QComboBox(self)
        self._type_combo.addItems(["one_to_one", "one_to_many"])
        self._header_row_input = QtWidgets.QLineEdit(self)
        self._header_row_input.setPlaceholderText("head or number (e.g. 4)")

        form.addWidget(QtWidgets.QLabel("From field:", self), 0, 0)
        form.addWidget(self._from_field, 0, 1)
        form.addWidget(QtWidgets.QLabel("To table:", self), 1, 0)
        form.addWidget(self._to_table, 1, 1)
        form.addWidget(QtWidgets.QLabel("To field:", self), 2, 0)
        form.addWidget(self._to_field, 2, 1)
        form.addWidget(QtWidgets.QLabel("Relation type:", self), 3, 0)
        form.addWidget(self._type_combo, 3, 1)
        form.addWidget(QtWidgets.QLabel("Header row:", self), 4, 0)
        form.addWidget(self._header_row_input, 4, 1)

        self._add_btn = QtWidgets.QPushButton("Add Relation", self)
        form.addWidget(self._add_btn, 5, 1)
        layout.addLayout(form)

        layout.addWidget(QtWidgets.QLabel("Existing relations:", self))
        self._relations_list = QtWidgets.QListWidget(self)
        self._relations_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        layout.addWidget(self._relations_list)

        button_row = QtWidgets.QHBoxLayout()
        self._remove_btn = QtWidgets.QPushButton("Remove Selected", self)
        close_btn = QtWidgets.QPushButton("Close", self)
        button_row.addWidget(self._remove_btn)
        button_row.addStretch(1)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        self._to_table.currentTextChanged.connect(self._refresh_to_fields)
        self._header_row_input.editingFinished.connect(self._on_header_row_changed)
        self._add_btn.clicked.connect(self._add_relation)
        self._remove_btn.clicked.connect(self._remove_selected)
        close_btn.clicked.connect(self.close)

        self.refresh_state()

    def refresh_state(self) -> None:
        current = self._main_window._relation_current_table()
        if current:
            self._current_label.setText(f"Current table: {current}")
        else:
            self._current_label.setText("Current table: (none)")
        self._header_row_input.setText(self._main_window._relation_header_setting())
        self._refresh_from_fields()
        self._refresh_to_tables()
        self._refresh_relations()
        self._add_btn.setEnabled(bool(current))

    def _refresh_from_fields(self) -> None:
        self._from_field.clear()
        fields = self._main_window._relation_current_fields()
        self._from_field.addItems(fields)

    def _refresh_to_tables(self) -> None:
        self._to_table.clear()
        tables = self._main_window._relation_tables()
        current = self._main_window._relation_current_table()
        if current:
            tables = [table for table in tables if table != current]
        self._to_table.addItems(tables)
        self._refresh_to_fields()

    def _refresh_to_fields(self) -> None:
        self._to_field.clear()
        table = self._to_table.currentText()
        if not table:
            return
        fields = self._main_window._relation_table_fields(table)
        self._to_field.addItems(fields)

    def _on_header_row_changed(self) -> None:
        value = self._header_row_input.text().strip()
        if not value:
            return
        self._main_window._set_relation_header_setting(value)
        self._refresh_from_fields()
        self._refresh_to_fields()

    def _refresh_relations(self) -> None:
        self._relations_list.clear()
        relations = self._main_window._relation_list()
        for rel in relations:
            text = (
                f"{rel['from_table']}.{rel['from_field']} -> "
                f"{rel['to_table']}.{rel['to_field']} ({rel['type']})"
            )
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, rel)
            self._relations_list.addItem(item)

    def _add_relation(self) -> None:
        current = self._main_window._relation_current_table()
        if not current:
            return
        from_field = self._from_field.currentText().strip()
        to_table = self._to_table.currentText().strip()
        to_field = self._to_field.currentText().strip()
        rel_type = self._type_combo.currentText().strip()
        if not (from_field and to_table and to_field and rel_type):
            return
        relation = {
            "from_table": current,
            "from_field": from_field,
            "to_table": to_table,
            "to_field": to_field,
            "type": rel_type,
        }
        self._main_window._relation_add(relation)
        self._refresh_relations()

    def _remove_selected(self) -> None:
        selected = self._relations_list.selectedItems()
        if not selected:
            return
        relations = []
        for item in selected:
            rel = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(rel, dict):
                relations.append(rel)
        if relations:
            self._main_window._relation_delete(relations)
        self._refresh_relations()
