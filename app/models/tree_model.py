"""Модель дерева навигации по логу.

Иерархия:
    📁 Файл
      ├── 🔴 ERROR (N)
      │     ├── 🕐 2025-03-15 10:00-11:00 (M)
      │     └── ...
      ├── 🟡 WARN (N)
      └── 🔵 INFO (N)

Уровни-дети раскрываются лениво при первом клике (hasChildren возвращает True
без фактической загрузки; загрузка происходит по expanded-сигналу из view
через populate_children).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from PyQt6.QtCore import QAbstractItemModel, QModelIndex, Qt, QVariant
from PyQt6.QtGui import QBrush, QColor

from app.config import LIGHT_THEME
from app.db.repository import Repository


@dataclass
class TreeNode:
    """Узел дерева."""
    title: str
    kind: str                       # "file" | "level" | "hour"
    line_number: int = 0            # к какой строке вести при двойном клике
    count: int = 0                  # сколько строк в этой группе
    level: Optional[str] = None     # ERROR/WARN/...
    parent: Optional["TreeNode"] = None
    children: List["TreeNode"] = field(default_factory=list)
    populated: bool = False         # True, если дети уже подгружены


class NavigationTreeModel(QAbstractItemModel):
    """Ленивая модель дерева (QAbstractItemModel)."""

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self._repo = repo
        self._root: Optional[TreeNode] = None
        self._theme = LIGHT_THEME

    def set_file(self, file_id: int, file_path: str) -> None:
        """Построить корень дерева для указанного файла (уровни)."""
        self.beginResetModel()

        file_row = self._repo.get_file(file_id)
        total = file_row["total_lines"] if file_row else 0

        root = TreeNode(
            title=f"📄 {file_path}  ({total:,} строк)".replace(",", " "),
            kind="file",
        )
        # Уровни — дети корня
        counts = self._repo.count_by_level(file_id)
        for level in ("ERROR", "WARN", "INFO", "DEBUG", "TRACE"):
            if level in counts:
                icon = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵",
                        "DEBUG": "⚪", "TRACE": "⚫"}[level]
                lvl_node = TreeNode(
                    title=f"{icon} {level} ({counts[level]:,} строк)".replace(",", " "),
                    kind="level",
                    level=level,
                    count=counts[level],
                    parent=root,
                )
                root.children.append(lvl_node)
        root.populated = True

        self._file_id = file_id
        self._root = root
        self.endResetModel()


    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if self._root is None:
            return 0
        node = self._node(parent)
        return len(node.children)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 1

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:  # noqa: B008,E501
        if self._root is None:
            return QModelIndex()
        parent_node = self._node(parent)
        if 0 <= row < len(parent_node.children):
            return self.createIndex(row, column, parent_node.children[row])
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:  # type: ignore[override]
        if not index.isValid():
            return QModelIndex()
        node: TreeNode = index.internalPointer()
        if node.parent is None or node.parent is self._root:
            return QModelIndex()
        grand = node.parent.parent
        if grand is None:
            return QModelIndex()
        row = grand.children.index(node.parent)
        return self.createIndex(row, 0, node.parent)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()
        node: TreeNode = index.internalPointer()
        if role == Qt.ItemDataRole.DisplayRole:
            return node.title
        if role == Qt.ItemDataRole.BackgroundRole and node.level:
            color = self._theme.get(node.level)
            if color:
                return QBrush(QColor(color))
        return QVariant()


    def hasChildren(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: B008
        if self._root is None:
            return False
        node = self._node(parent)
        if node.kind == "level":
            return True  # детей ещё не загружали, но они есть
        return bool(node.children)

    def canFetchMore(self, parent: QModelIndex) -> bool:
        if not parent.isValid():
            return False
        node: TreeNode = parent.internalPointer()
        return node.kind == "level" and not node.populated

    def fetchMore(self, parent: QModelIndex) -> None:
        if not parent.isValid():
            return
        node: TreeNode = parent.internalPointer()
        if node.kind != "level" or node.populated:
            return

        # Загружаем дочерние узлы — группы по часам
        rows = self._repo.get_indexes(self._file_id, levels=[node.level])
        # Агрегируем по часу (первые 13 символов timestamp: "YYYY-MM-DD HH")
        hours: dict[str, tuple[int, int]] = {}
        for r in rows:
            ts = r["timestamp"] or "без времени"
            key = ts[:13] if len(ts) >= 13 else ts
            cnt, first_line = hours.get(key, (0, r["line_number"]))
            hours[key] = (cnt + 1, first_line)

        # Создаём узлы-дети
        children = []
        for hour, (cnt, first_line) in sorted(hours.items()):
            child = TreeNode(
                title=f"🕐 {hour}  ({cnt})",
                kind="hour",
                count=cnt,
                level=node.level,
                line_number=first_line,
                parent=node,
            )
            children.append(child)

        if children:
            self.beginInsertRows(parent, 0, len(children) - 1)
            node.children = children
            node.populated = True
            self.endInsertRows()
        else:
            node.populated = True


    def set_theme(self, theme: dict) -> None:
        self._theme = theme


    def _node(self, index: QModelIndex) -> TreeNode:
        if not index.isValid():
            return self._root  # type: ignore[return-value]
        return index.internalPointer()  # type: ignore[return-value]

    @staticmethod
    def line_number_from_index(index: QModelIndex) -> int:
        if not index.isValid():
            return 0
        node: TreeNode = index.internalPointer()
        return node.line_number
