"""Форма 4: Дерево навигации.

Обёртка над QTreeView с моделью NavigationTreeModel.
Эмитит сигнал nodeActivated(line_number) при двойном клике.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTreeView, QWidget, QVBoxLayout, QLabel

from app.models.tree_model import NavigationTreeModel


class NavigationTreeWidget(QWidget):
    """Дерево навигации по логу (файл → уровень → час)."""

    nodeActivated = pyqtSignal(int)  # line_number

    def __init__(self, parent=None):
        super().__init__(parent)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        self._title = QLabel("Навигация")
        f = self._title.font()
        f.setBold(True)
        self._title.setFont(f)
        lay.addWidget(self._title)

        self._tree = QTreeView(self)
        self._tree.setHeaderHidden(True)
        self._tree.setExpandsOnDoubleClick(False)
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.clicked.connect(self._on_click)
        lay.addWidget(self._tree)

        self._model: Optional[NavigationTreeModel] = None

    def set_model(self, model: NavigationTreeModel) -> None:
        self._model = model
        self._tree.setModel(model)
        self._tree.expandToDepth(0)

    def expand_all(self) -> None:
        """Раскрыть все узлы (для команды «Показать в дереве»)."""
        self._tree.expandAll()

    def _on_click(self, index) -> None:
        # Одиночный клик — раскрывает/сворачивает узел
        if self._tree.isExpanded(index):
            self._tree.collapse(index)
        else:
            self._tree.expand(index)

    def _on_double_click(self, index) -> None:
        if self._model is None:
            return
        line_number = NavigationTreeModel.line_number_from_index(index)
        if line_number > 0:
            self.nodeActivated.emit(line_number)
