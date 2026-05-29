"""Форма 6: Диалог поиска.

Находит совпадения в видимых строках (в пределах текущего фильтра).
Подсвечивает совпадения через LogTableModel.set_search_hits().
Позволяет переходить между результатами.
"""
from __future__ import annotations

import re
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.models.log_model import LogTableModel


class SearchDialog(QDialog):
    """Диалог поиска с навигацией по результатам."""

    def __init__(self, model: LogTableModel, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Поиск")
        self.resize(600, 400)
        self._model = model
        self._hits: List[int] = []  # номера строк (line_number)
        self._current = -1

        lay = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Найти:"))
        self._edit = QLineEdit()
        self._edit.returnPressed.connect(self._do_search)
        row1.addWidget(self._edit, stretch=1)

        self._cb_regex = QCheckBox("regex")
        row1.addWidget(self._cb_regex)

        self._cb_case = QCheckBox("Aa")
        self._cb_case.setToolTip("Учитывать регистр")
        row1.addWidget(self._cb_case)

        self._cb_whole = QCheckBox("Слово")
        self._cb_whole.setToolTip("Только целые слова")
        row1.addWidget(self._cb_whole)

        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self._btn_find = QPushButton("Найти")
        self._btn_find.clicked.connect(self._do_search)
        row2.addWidget(self._btn_find)

        self._btn_prev = QPushButton("◀ Пред.")
        self._btn_prev.clicked.connect(self._prev)
        row2.addWidget(self._btn_prev)

        self._btn_next = QPushButton("След. ▶")
        self._btn_next.clicked.connect(self._next)
        row2.addWidget(self._btn_next)

        self._btn_clear = QPushButton("Сбросить подсветку")
        self._btn_clear.clicked.connect(self._clear)
        row2.addWidget(self._btn_clear)

        row2.addStretch()
        lay.addLayout(row2)

        lay.addWidget(QLabel("Результаты:"))
        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._jump_to)
        lay.addWidget(self._list, stretch=1)

        self._status = QLabel("")
        lay.addWidget(self._status)


    def _compile_pattern(self) -> Optional[re.Pattern]:
        text = self._edit.text().strip()
        if not text:
            return None

        flags = 0 if self._cb_case.isChecked() else re.IGNORECASE
        if self._cb_regex.isChecked():
            try:
                return re.compile(text, flags)
            except re.error as e:
                QMessageBox.warning(self, "Ошибка регулярки", str(e))
                return None

        if self._cb_whole.isChecked():
            return re.compile(rf"\b{re.escape(text)}\b", flags)
        return re.compile(re.escape(text), flags)

    def _do_search(self) -> None:
        pat = self._compile_pattern()
        if pat is None:
            return

        self._hits = []
        self._list.clear()
        # Нужно прогнать модель до конца — подгружаем все строки
        while self._model.canFetchMore():
            self._model.fetchMore()

        rows = self._model.rowCount()
        max_hits = 10_000  # защита от переполнения
        for row in range(rows):
            info = self._model.get_line_info(row)
            if not info:
                continue
            line_number, byte_offset, length, level, ts = info
            # _get_text приватный, но это ок — внутри приложения
            text = self._model._get_text(line_number, byte_offset, length)  # noqa: SLF001
            m = pat.search(text)
            if m:
                self._hits.append(line_number)
                preview = text[:120]
                item = QListWidgetItem(f"[{line_number}] {preview}")
                item.setData(Qt.ItemDataRole.UserRole, line_number)
                self._list.addItem(item)
                if len(self._hits) >= max_hits:
                    break

        if not self._hits:
            self._status.setText("Ничего не найдено")
            self._model.clear_search_hits()
            return

        self._status.setText(f"Найдено: {len(self._hits)}")
        self._model.set_search_hits(set(self._hits))
        self._current = 0

    def _jump_to(self, item: QListWidgetItem) -> None:
        line_number = item.data(Qt.ItemDataRole.UserRole)
        if line_number is None:
            return
        row = self._model.find_row_by_line_number(line_number)
        # Достучаться до главного окна и прокрутить таблицу
        main = self.parent()
        while main and not hasattr(main, "_log_view"):
            main = main.parent()
        if main and hasattr(main, "_log_view"):
            main._log_view.scroll_to_row(row)  # noqa: SLF001

    def _next(self) -> None:
        if not self._hits:
            return
        self._current = (self._current + 1) % len(self._hits)
        self._jump_to_current()

    def _prev(self) -> None:
        if not self._hits:
            return
        self._current = (self._current - 1) % len(self._hits)
        self._jump_to_current()

    def _jump_to_current(self) -> None:
        line = self._hits[self._current]
        self._status.setText(f"Результат {self._current + 1} из {len(self._hits)}")
        item = self._list.item(self._current)
        if item:
            self._list.setCurrentItem(item)
            self._jump_to(item)

    def _clear(self) -> None:
        self._model.clear_search_hits()
        self._list.clear()
        self._hits = []
        self._current = -1
        self._status.setText("")
