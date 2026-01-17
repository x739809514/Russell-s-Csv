import csv
from dataclasses import dataclass
from typing import List, Optional

from PyQt6 import QtCore


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
