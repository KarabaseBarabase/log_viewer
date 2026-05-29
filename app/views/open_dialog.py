"""Форма 2: Расширенный диалог открытия файла.

Содержит:
    - QTreeView с файловой системой (QFileSystemModel)
    - Список недавних файлов (QListWidget)
    - Область предпросмотра первых 10 строк (лениво — читает только head)
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QDir
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from app.db.repository import Repository


class OpenFileDialog(QDialog):
    """Расширенный диалог открытия лог-файла."""

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Открыть лог-файл")
        self.resize(1000, 600)
        self._repo = repo
        self._selected: Optional[str] = None

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Левая часть: дерево ФС
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(QLabel("Файловая система:"))

        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath(QDir.homePath())
        # Фильтрация (показываем .log/.txt/.out и все папки)
        self._fs_model.setNameFilters(["*.log", "*.txt", "*.out"])
        self._fs_model.setNameFilterDisables(False)

        self._tree = QTreeView()
        self._tree.setModel(self._fs_model)
        self._tree.setRootIndex(self._fs_model.index(QDir.homePath()))
        self._tree.setColumnWidth(0, 300)
        self._tree.clicked.connect(self._on_tree_click)
        self._tree.doubleClicked.connect(self._on_tree_double_click)
        ll.addWidget(self._tree)

        splitter.addWidget(left)

        # Правая часть: недавние + предпросмотр
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        rl.addWidget(QLabel("Недавно открытые:"))
        self._recent = QListWidget()
        self._recent.itemClicked.connect(self._on_recent_click)
        self._recent.itemDoubleClicked.connect(self._on_recent_double_click)
        for path in self._repo.recent(15):
            item = QListWidgetItem(path)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._recent.addItem(item)
        rl.addWidget(self._recent, stretch=1)

        rl.addWidget(QLabel("Предпросмотр (первые 10 строк):"))
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        f = self._preview.font()
        f.setFamily("Consolas, Menlo, Courier New")
        self._preview.setFont(f)
        rl.addWidget(self._preview, stretch=2)

        splitter.addWidget(right)
        splitter.setSizes([500, 500])

        # Кнопки
        btn = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel
        )
        btn.accepted.connect(self.accept)
        btn.rejected.connect(self.reject)
        self._btn_open = btn.button(QDialogButtonBox.StandardButton.Open)
        self._btn_open.setEnabled(False)

        main = QVBoxLayout(self)
        main.addWidget(splitter, stretch=1)
        main.addWidget(btn)

    def selected_path(self) -> Optional[str]:
        return self._selected


    def _on_tree_click(self, index) -> None:
        path = self._fs_model.filePath(index)
        if os.path.isfile(path):
            self._select(path)

    def _on_tree_double_click(self, index) -> None:
        path = self._fs_model.filePath(index)
        if os.path.isfile(path):
            self._select(path)
            self.accept()

    def _on_recent_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self._select(path)

    def _on_recent_double_click(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self._select(path)
            self.accept()

    def _select(self, path: str) -> None:
        self._selected = path
        self._btn_open.setEnabled(True)
        # Ленивый предпросмотр: читаем только первые 10 строк
        try:
            lines = []
            with open(path, "rb") as f:
                for i, raw in enumerate(f):
                    if i >= 10:
                        break
                    try:
                        lines.append(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
                    except Exception:
                        lines.append("<binary>")
            self._preview.setPlainText("\n".join(lines))
        except Exception as e:
            self._preview.setPlainText(f"<не удалось прочитать: {e}>")
