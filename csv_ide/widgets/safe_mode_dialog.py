from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING

from PyQt6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from csv_ide.windows.main_window import MainWindow


class SafeModeDialog(QtWidgets.QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self._main_window = parent
        self._settings = parent._settings
        self.setWindowTitle("Safe Mode")
        self.setModal(False)

        layout = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QGridLayout()
        interval_label = QtWidgets.QLabel("Backup interval (minutes):", self)
        self._interval_spin = QtWidgets.QSpinBox(self)
        self._interval_spin.setRange(1, 1440)
        self._interval_spin.setSuffix(" min")

        retention_label = QtWidgets.QLabel("Keep backups (days):", self)
        self._retention_spin = QtWidgets.QSpinBox(self)
        self._retention_spin.setRange(1, 3650)
        self._retention_spin.setSuffix(" days")

        path_label = QtWidgets.QLabel("Backup folder:", self)
        self._path_input = QtWidgets.QLineEdit(self)
        self._browse_btn = QtWidgets.QPushButton("Browse...", self)

        form.addWidget(interval_label, 0, 0)
        form.addWidget(self._interval_spin, 0, 1)
        form.addWidget(retention_label, 1, 0)
        form.addWidget(self._retention_spin, 1, 1)
        form.addWidget(path_label, 2, 0)
        form.addWidget(self._path_input, 2, 1)
        form.addWidget(self._browse_btn, 2, 2)
        layout.addLayout(form)

        files_label = QtWidgets.QLabel("Safe mode files:", self)
        self._files_list = QtWidgets.QListWidget(self)
        self._files_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )

        files_button_row = QtWidgets.QHBoxLayout()
        self._add_selected_btn = QtWidgets.QPushButton("Add Selected", self)
        self._add_file_btn = QtWidgets.QPushButton("Add File...", self)
        self._remove_btn = QtWidgets.QPushButton("Remove Selected", self)
        self._clear_btn = QtWidgets.QPushButton("Clear", self)
        files_button_row.addWidget(self._add_selected_btn)
        files_button_row.addWidget(self._add_file_btn)
        files_button_row.addWidget(self._remove_btn)
        files_button_row.addWidget(self._clear_btn)
        files_button_row.addStretch(1)

        layout.addWidget(files_label)
        layout.addWidget(self._files_list)
        layout.addLayout(files_button_row)

        log_label = QtWidgets.QLabel("Backed up files:", self)
        self._log_list = QtWidgets.QListWidget(self)
        self._log_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._backup_now_btn = QtWidgets.QPushButton("Backup Now", self)
        self._reload_btn = QtWidgets.QPushButton("Reload Selected Backup", self)
        self._reload_btn.setEnabled(False)
        self._reload_btn.setVisible(False)
        self._delete_btn = QtWidgets.QPushButton("Delete Selected Backups", self)
        self._delete_btn.setEnabled(False)

        layout.addWidget(log_label)
        layout.addWidget(self._log_list)
        layout.addWidget(self._backup_now_btn)
        layout.addWidget(self._reload_btn)
        layout.addWidget(self._delete_btn)

        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch(1)
        close_btn = QtWidgets.QPushButton("Close", self)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._browse_btn.clicked.connect(self._choose_folder)
        self._interval_spin.valueChanged.connect(self._persist_settings)
        self._retention_spin.valueChanged.connect(self._persist_settings)
        self._path_input.editingFinished.connect(self._persist_settings)
        self._add_selected_btn.clicked.connect(self._add_selected_files)
        self._add_file_btn.clicked.connect(self._add_files_via_dialog)
        self._remove_btn.clicked.connect(self._remove_selected_files)
        self._clear_btn.clicked.connect(self._clear_files)
        self._log_list.itemSelectionChanged.connect(self._on_log_selection_changed)
        self._reload_btn.clicked.connect(self._reload_selected_backup)
        self._delete_btn.clicked.connect(self._delete_selected_backups)
        self._backup_now_btn.clicked.connect(self._backup_now)

        self._load_settings()

    def refresh_state(self) -> None:
        self._load_settings()

    def _load_settings(self) -> None:
        interval = self._settings.value("safe_mode_interval_min", 5, type=int)
        retention = self._settings.value("safe_mode_retention_days", 7, type=int)
        backup_path = self._settings.value("safe_mode_backup_path", "", type=str)
        files = self._settings.value("safe_mode_files", [], type=list)
        log = self._settings.value("safe_mode_backup_log", [], type=list)

        self._interval_spin.setValue(max(1, int(interval)))
        self._retention_spin.setValue(max(1, int(retention)))
        self._path_input.setText(backup_path)
        self._set_file_list([path for path in files if isinstance(path, str)])
        self.refresh_log([entry for entry in log if isinstance(entry, str)])

    def refresh_log(self, entries: list[str]) -> None:
        self._log_list.clear()
        for entry in entries:
            item = QtWidgets.QListWidgetItem(entry)
            backup_path = self._extract_backup_path(entry)
            if backup_path:
                item.setData(QtCore.Qt.ItemDataRole.UserRole, backup_path)
            self._log_list.addItem(item)
        self._reload_btn.setEnabled(False)
        self._reload_btn.setVisible(False)

    def _choose_folder(self) -> None:
        start = self._path_input.text().strip() or self._main_window._root_path
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Backup Folder", start)
        if not path:
            return
        self._path_input.setText(path)
        self._persist_settings()

    def _set_file_list(self, paths: list[str]) -> None:
        self._files_list.clear()
        for path in sorted(set(paths)):
            if not path:
                continue
            item = QtWidgets.QListWidgetItem(os.path.basename(path))
            item.setToolTip(path)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
            self._files_list.addItem(item)

    def _current_files(self) -> list[str]:
        paths: list[str] = []
        for i in range(self._files_list.count()):
            item = self._files_list.item(i)
            path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(path, str):
                paths.append(path)
        return paths

    def _add_selected_files(self) -> None:
        selected = self._main_window._selected_paths()
        self._merge_files(selected)

    def _add_files_via_dialog(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Add CSV Files",
            self._main_window._root_path,
            "CSV Files (*.csv *.tsv)",
        )
        if paths:
            self._merge_files(paths)

    def _merge_files(self, new_paths: list[str]) -> None:
        current = set(self._current_files())
        for path in new_paths:
            if isinstance(path, str):
                current.add(path)
        self._set_file_list(sorted(current))
        self._persist_settings()

    def _remove_selected_files(self) -> None:
        for item in self._files_list.selectedItems():
            row = self._files_list.row(item)
            self._files_list.takeItem(row)
        self._persist_settings()

    def _clear_files(self) -> None:
        self._files_list.clear()
        self._persist_settings()

    def _persist_settings(self) -> None:
        interval = int(self._interval_spin.value())
        retention = int(self._retention_spin.value())
        backup_path = self._path_input.text().strip()
        files = self._current_files()

        self._settings.setValue("safe_mode_interval_min", interval)
        self._settings.setValue("safe_mode_retention_days", retention)
        self._settings.setValue("safe_mode_backup_path", backup_path)
        self._settings.setValue("safe_mode_files", files)
        self._main_window._configure_safe_mode_timer()

    def _extract_backup_path(self, entry: str) -> str:
        if " -> " not in entry:
            return ""
        return entry.split(" -> ", 1)[1].strip()

    def _on_log_selection_changed(self) -> None:
        selected = self._log_list.selectedItems()
        if not selected:
            self._reload_btn.setEnabled(False)
            self._reload_btn.setVisible(False)
            self._delete_btn.setEnabled(False)
            return
        first_path = selected[0].data(QtCore.Qt.ItemDataRole.UserRole)
        enabled = isinstance(first_path, str) and bool(first_path)
        self._reload_btn.setEnabled(enabled)
        self._reload_btn.setVisible(enabled)
        self._delete_btn.setEnabled(True)

    def _reload_selected_backup(self) -> None:
        selected = self._log_list.selectedItems()
        if not selected:
            return
        backup_path = selected[0].data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(backup_path, str) or not backup_path:
            return
        message = (
            "Apply this backup? This will overwrite the existing file contents."
        )
        result = QtWidgets.QMessageBox.question(
            self,
            "Apply Backup",
            message,
            QtWidgets.QMessageBox.StandardButton.Ok
            | QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if result != QtWidgets.QMessageBox.StandardButton.Ok:
            return
        self._main_window._restore_safe_mode_backup(backup_path)

    def _delete_selected_backups(self) -> None:
        selected = self._log_list.selectedItems()
        if not selected:
            return
        result = QtWidgets.QMessageBox.question(
            self,
            "Delete Backups",
            "Delete the selected backups from disk?",
            QtWidgets.QMessageBox.StandardButton.Ok
            | QtWidgets.QMessageBox.StandardButton.Cancel,
        )
        if result != QtWidgets.QMessageBox.StandardButton.Ok:
            return
        backup_paths = []
        for item in selected:
            path = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(path, str) and path:
                backup_paths.append(path)
        if backup_paths:
            self._main_window._delete_safe_mode_backups(backup_paths)

    def _backup_now(self) -> None:
        self._main_window._run_safe_mode_backup()
