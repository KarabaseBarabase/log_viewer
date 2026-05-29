"""Форма 3: Основной просмотрщик логов.

Содержит:
    - QTableView, подключённый к ленивой LogTableModel
    - Фиксированная колонка номеров строк (уже в модели)
    - Мини-карта (MinimapWidget) справа от таблицы — heatmap ошибок
    - Подсветка строк цветом уровня (делает модель через BackgroundRole)
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QSizePolicy,
    QTableView,
    QWidget,
)

from app.models.log_model import LogTableModel
from app.views.minimap import MinimapWidget


class LogViewerWidget(QWidget):
    """Просмотрщик логов: таблица + мини-карта."""

    # Эмитится при выборе пункта «Показать в дереве» из контекстного меню.
    # MainWindow подключает его к разворачиванию узла дерева навигации.
    showInTreeRequested = pyqtSignal(int)  # line_number

    def __init__(self, parent=None):
        super().__init__(parent)

        self._model: Optional[LogTableModel] = None

        # Таблица
        self._table = QTableView(self)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        # Колонки: первые три по содержимому, последняя растягивается на всё свободное место
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(True)

        # Контекстное меню по правому клику
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        # Мини-карта ошибок. Каждая красная полоска — диапазон файла с ERROR-строками,
        # яркость = плотность ошибок. Клик переносит курсор в эту позицию файла.
        self._minimap = MinimapWidget(self)
        self._minimap.setFixedWidth(20)
        self._minimap.setToolTip(
            "Карта ошибок по файлу. Красные блоки — участки с ERROR-строками,\n"
            "интенсивность отражает плотность ошибок. Клик — переход к позиции."
        )
        self._minimap.positionClicked.connect(self._on_minimap_click)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._table, stretch=1)
        lay.addWidget(self._minimap, stretch=0)

    def set_model(self, model: LogTableModel) -> None:
        self._model = model
        self._table.setModel(model)
        # Моноширинный шрифт для удобного чтения логов
        f = QFont("Consolas", 11)
        self._table.setFont(f)

    def set_table_font(self, family: str, size: int) -> None:
        """Применить новый шрифт к таблице (вызывается из настроек)."""
        # QFont принимает основное имя семьи; берём первое из CSV-списка
        primary = family.split(",")[0].strip()
        f = QFont(primary, size)
        self._table.setFont(f)
        # Перерисовать строки с новой высотой
        self._table.resizeRowsToContents()

    def set_heatmap(self, data: List[int]) -> None:
        self._minimap.set_data(data)

    def scroll_to_row(self, row: int) -> None:
        if row < 0 or self._model is None:
            return
        idx = self._model.index(row, 0)
        self._table.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
        self._table.selectRow(row)

    def _on_minimap_click(self, fraction: float) -> None:
        """Клик по мини-карте — прыгаем на соответствующую строку."""
        if self._model is None or self._model.rowCount() == 0:
            return
        # Докачиваем модель до конца, чтобы scrollTo нашёл нужную строку
        while self._model.canFetchMore():
            self._model.fetchMore()
        row = int(fraction * (self._model.rowCount() - 1))
        self.scroll_to_row(row)

    def _show_context_menu(self, pos) -> None:
        """Меню по правому клику: Копировать / Скопировать строку / Перейти к ошибке."""
        if self._model is None:
            return
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()

        menu = QMenu(self)

        act_copy_text = QAction("Копировать (только текст)", self)
        act_copy_text.triggered.connect(lambda: self._copy_cell_text(row))
        menu.addAction(act_copy_text)

        act_copy_full = QAction("Копировать строку целиком", self)
        act_copy_full.triggered.connect(lambda: self._copy_full_row(row))
        menu.addAction(act_copy_full)

        menu.addSeparator()

        act_next_err = QAction("Перейти к следующей ошибке", self)
        act_next_err.triggered.connect(lambda: self._jump_to_error(row, direction=+1))
        menu.addAction(act_next_err)

        act_prev_err = QAction("Перейти к предыдущей ошибке", self)
        act_prev_err.triggered.connect(lambda: self._jump_to_error(row, direction=-1))
        menu.addAction(act_prev_err)

        menu.addSeparator()

        act_show_tree = QAction("Показать в дереве навигации", self)
        # line_number нужен дереву — берём из модели
        line_number = self._model.line_number_at(row)
        act_show_tree.triggered.connect(lambda: self.showInTreeRequested.emit(line_number))
        menu.addAction(act_show_tree)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _copy_cell_text(self, row: int) -> None:
        """Копирует в буфер только содержимое колонки «Сообщение»."""
        text = self._model.text_at(row)
        QGuiApplication.clipboard().setText(text)

    def _copy_full_row(self, row: int) -> None:
        """Копирует строку как «№\\tуровень\\tвремя\\tтекст»."""
        n, level, ts, text = self._model.row_tuple_at(row)
        line = f"{n}\t{level or ''}\t{ts or ''}\t{text}"
        QGuiApplication.clipboard().setText(line)

    def _jump_to_error(self, from_row: int, direction: int) -> None:
        """Переход к ближайшей ERROR/WARN строке вверх или вниз от текущей."""
        target = self._model.find_error_row(from_row, direction)
        if target is not None:
            self.scroll_to_row(target)
