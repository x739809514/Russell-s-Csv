import os
import tempfile
import time
import unittest
from pathlib import Path

from PyQt6 import QtCore, QtWidgets

from csv_ide.windows.main_window import MainWindow


class FileListRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
        QtCore.QSettings.setPath(
            QtCore.QSettings.Format.IniFormat,
            QtCore.QSettings.Scope.UserScope,
            self.temp.name,
        )
        self.root = Path(self.temp.name) / "data"
        self.root.mkdir()
        (self.root / "before.csv").write_text("col\n", encoding="utf-8")
        QtCore.QSettings("RussellCsv", "RussellCsv").setValue("last_root_path", str(self.root))
        self.window = MainWindow()
        self.addCleanup(self.window.close)

    def paths(self) -> list[str]:
        paths = []
        for i in range(self.window._file_list.count()):
            item = self.window._file_list.item(i)
            assert item is not None
            paths.append(item.data(QtCore.Qt.ItemDataRole.UserRole))
        return paths

    def wait_for(self, predicate) -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.02)
        self.fail(f"file list did not update: {self.paths()}")

    def test_external_file_and_subfolder_changes(self) -> None:
        before = str(self.root / "before.csv")
        self.window._select_path(before)
        self.window._search_input.setText("before")
        after = self.root / "after.csv"
        after.write_text("col\n", encoding="utf-8")
        self.wait_for(lambda: str(after) in self.paths())
        after_item = self.window._file_list.item(self.paths().index(str(after)))
        assert after_item is not None
        self.assertTrue(after_item.isHidden())
        self.assertEqual(self.window._selected_paths(), [before])
        self.window._search_input.clear()
        self.assertFalse(after_item.isHidden())

        nested = self.root / "nested"
        nested.mkdir()
        self.wait_for(lambda: str(nested) in self.window._file_watcher.directories())
        child = nested / "child.tsv"
        child.write_text("col\n", encoding="utf-8")
        self.wait_for(lambda: str(child) in self.paths())
        child.unlink()
        self.wait_for(lambda: str(child) not in self.paths())

    def test_switch_folder_stops_watching_old_root(self) -> None:
        other = Path(self.temp.name) / "other"
        other.mkdir()
        self.window.open_folder(str(other))
        self.assertNotIn(str(self.root), self.window._file_watcher.directories())
        new_file = other / "new.csv"
        new_file.write_text("col\n", encoding="utf-8")
        self.wait_for(lambda: str(new_file) in self.paths())
        self.assertNotIn(str(self.root / "before.csv"), self.paths())


if __name__ == "__main__":
    unittest.main()
