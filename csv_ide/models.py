from dataclasses import dataclass
from typing import List, Optional

from PyQt6 import QtCore, QtGui


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
        self._row_colors: dict[int, str] = {}

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
        if role == QtCore.Qt.ItemDataRole.BackgroundRole:
            color = self._row_colors.get(index.row())
            if color:
                return QtGui.QBrush(QtGui.QColor(color))
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

    def setHeaderData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        value,
        role: int = QtCore.Qt.ItemDataRole.EditRole,
    ) -> bool:
        if orientation != QtCore.Qt.Orientation.Horizontal:
            return False
        if role != QtCore.Qt.ItemDataRole.EditRole:
            return False
        if section < 0:
            return False
        while section >= len(self._document.header):
            self._document.header.append("")
        self._document.header[section] = str(value)
        self.headerDataChanged.emit(orientation, section, section)
        return True

    def set_document(self, document: CsvDocument) -> None:
        self.beginResetModel()
        self._document = document
        self._normalize_row_colors()
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
        self._shift_row_colors_on_insert(row, count)
        self._emit_row_color_refresh(row)
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
        self._shift_row_colors_on_remove(row, end_row - row + 1)
        self._emit_row_color_refresh(row)
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

    def row_colors(self) -> dict[int, str]:
        return dict(self._row_colors)

    def set_row_color(self, row: int, color: Optional[str]) -> None:
        if row < 0 or row >= self.rowCount():
            return
        if color:
            self._row_colors[row] = color
        else:
            self._row_colors.pop(row, None)
        self._emit_row_color_changed(row)

    def set_row_colors(self, mapping: dict[int, str]) -> None:
        filtered: dict[int, str] = {}
        row_count = self.rowCount()
        for row, color in mapping.items():
            if isinstance(row, int) and 0 <= row < row_count and isinstance(color, str):
                filtered[row] = color
        self._row_colors = filtered
        self._emit_row_color_refresh(0)

    def _normalize_row_colors(self) -> None:
        row_count = self.rowCount()
        self._row_colors = {row: color for row, color in self._row_colors.items() if row < row_count}

    def _emit_row_color_changed(self, row: int) -> None:
        if self.rowCount() <= 0 or self.columnCount() <= 0:
            return
        start = self.index(row, 0)
        end = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(start, end, [QtCore.Qt.ItemDataRole.BackgroundRole])

    def _emit_row_color_refresh(self, start_row: int) -> None:
        if self.rowCount() <= 0 or self.columnCount() <= 0:
            return
        row = max(0, min(start_row, self.rowCount() - 1))
        start = self.index(row, 0)
        end = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(start, end, [QtCore.Qt.ItemDataRole.BackgroundRole])

    def _shift_row_colors_on_insert(self, row: int, count: int) -> None:
        if count <= 0 or not self._row_colors:
            return
        updated: dict[int, str] = {}
        for r, color in self._row_colors.items():
            if r >= row:
                updated[r + count] = color
            else:
                updated[r] = color
        self._row_colors = updated

    def _shift_row_colors_on_remove(self, row: int, count: int) -> None:
        if count <= 0 or not self._row_colors:
            return
        end_row = row + count - 1
        updated: dict[int, str] = {}
        for r, color in self._row_colors.items():
            if r < row:
                updated[r] = color
            elif r > end_row:
                updated[r - count] = color
        self._row_colors = updated
