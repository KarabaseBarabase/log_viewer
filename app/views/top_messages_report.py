"""Форма 8: Отчёт «Топ сообщений».

Таблица + горизонтальная гистограмма.
Двойной клик по строке — переход к первому вхождению.
"""
from __future__ import annotations

from typing import List, Tuple

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.db.repository import Repository


class TopMessagesDialog(QDialog):
    """Отчёт по самым частым уровням/сообщениям."""

    navigateTo = pyqtSignal(int)  # line_number

    def __init__(self, file_id: int, repo: Repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отчёт: топ сообщений")
        self.resize(900, 600)

        self._file_id = file_id
        self._repo = repo

        data = repo.top_messages(file_id, limit=10)
        # data: List[(level, count, last_timestamp)]

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<h3>Топ уровней по количеству строк</h3>"))
        lay.addWidget(QLabel(
            "<i>Упрощённая версия: агрегация выполняется по уровню логирования. "
            "Подробное разделение по уникальному тексту сообщения требует полного "
            "сканирования файла — реализовано в отчёте «Расширенная статистика».</i>"
        ))

        splitter = QSplitter(Qt.Orientation.Vertical)

        # Таблица
        tbl = QTableWidget(len(data), 4)
        tbl.setHorizontalHeaderLabels([
            "Уровень", "Количество", "Последнее появление", "Ранг"
        ])
        tbl.horizontalHeader().setStretchLastSection(True)
        for i, (level, count, last_ts) in enumerate(data):
            tbl.setItem(i, 0, QTableWidgetItem(level))
            it_cnt = QTableWidgetItem(str(count))
            it_cnt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tbl.setItem(i, 1, it_cnt)
            tbl.setItem(i, 2, QTableWidgetItem(last_ts))
            tbl.setItem(i, 3, QTableWidgetItem(f"#{i + 1}"))
        tbl.cellDoubleClicked.connect(lambda r, c: self._on_row_double_click(r, data))
        splitter.addWidget(tbl)

        # Горизонтальная гистограмма
        plot_widget = QWidget()
        pl = QVBoxLayout(plot_widget)
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")
        plot = pg.PlotWidget()
        plot.setLabel("bottom", "Количество")
        plot.showGrid(x=True, alpha=0.3)
        if data:
            y = list(range(len(data)))
            w = [cnt for _, cnt, _ in data]
            bar = pg.BarGraphItem(
                x0=[0] * len(data),
                y=y,
                width=w,
                height=0.6,
                brush="#4080D0",
            )
            plot.addItem(bar)
            ax = plot.getAxis("left")
            ticks = [(i, data[i][0]) for i in range(len(data))]
            ax.setTicks([ticks])
        pl.addWidget(plot)
        splitter.addWidget(plot_widget)

        splitter.setSizes([300, 300])
        lay.addWidget(splitter, stretch=1)

        # Кнопка закрытия
        btns = QHBoxLayout()
        btns.addStretch()
        btn = QPushButton("Закрыть")
        btn.clicked.connect(self.accept)
        btns.addWidget(btn)
        lay.addLayout(btns)

        self._data = data

    def _on_row_double_click(self, row: int, data: List[Tuple[str, int, str]]) -> None:
        if 0 <= row < len(data):
            level = data[row][0]
            # Ищем первую строку этого уровня
            rows = self._repo.get_indexes(self._file_id, levels=[level], limit=1)
            if rows:
                self.navigateTo.emit(rows[0]["line_number"])
                self.accept()
