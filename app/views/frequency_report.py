"""Форма 7: Отчёт по частоте ошибок по времени.

График (гистограмма) + таблица с детализацией (час, количество, %).
Использует pyqtgraph для отрисовки.
"""
from __future__ import annotations

from typing import List, Tuple

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.db.repository import Repository


class FrequencyReportDialog(QDialog):
    """Отчёт: частота ошибок по часам."""

    def __init__(self, file_id: int, repo: Repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Отчёт: частота ошибок по времени")
        self.resize(1000, 700)
        self._file_id = file_id
        self._repo = repo

        data = self._repo.errors_per_hour(file_id)
        # data: List[(hour_str, count)]

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<h3>Частота ошибок (ERROR) по часам</h3>"))

        # График
        pg.setConfigOption("background", "w")
        pg.setConfigOption("foreground", "k")
        self._plot = pg.PlotWidget()
        self._plot.setLabel("left", "Количество ошибок")
        self._plot.setLabel("bottom", "Часы (индекс)")
        self._plot.showGrid(x=True, y=True, alpha=0.3)

        if data:
            x = list(range(len(data)))
            y = [c for _, c in data]
            bar = pg.BarGraphItem(x=x, height=y, width=0.8, brush="#D04040")
            self._plot.addItem(bar)

            # Подписи по оси X (часы)
            ax = self._plot.getAxis("bottom")
            # Показываем не все метки, а каждую N-ю, чтобы не слипались
            step = max(1, len(data) // 15)
            ticks = [(i, data[i][0][-5:]) for i in range(0, len(data), step)]
            ax.setTicks([ticks])

        lay.addWidget(self._plot, stretch=3)

        # Таблица с детализацией
        lay.addWidget(QLabel("<b>Детализация:</b>"))
        total = sum(c for _, c in data) or 1
        self._table = QTableWidget(len(data), 3)
        self._table.setHorizontalHeaderLabels(["Час", "Количество", "% от всех ошибок"])
        self._table.horizontalHeader().setStretchLastSection(True)
        for i, (hour, count) in enumerate(data):
            self._table.setItem(i, 0, QTableWidgetItem(hour))
            it_cnt = QTableWidgetItem(str(count))
            it_cnt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, 1, it_cnt)
            pct = count * 100 / total
            it_pct = QTableWidgetItem(f"{pct:.2f}%")
            it_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(i, 2, it_pct)
        lay.addWidget(self._table, stretch=2)

        # Кнопки
        btns = QHBoxLayout()
        btns.addStretch()
        btn_export_png = QPushButton("Сохранить график (PNG)")
        btn_export_png.clicked.connect(self._export_png)
        btns.addWidget(btn_export_png)

        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        btns.addWidget(btn_close)
        lay.addLayout(btns)

    def _export_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить график как PNG", "frequency_report.png", "PNG (*.png)"
        )
        if not path:
            return
        try:
            exporter = pg.exporters.ImageExporter(self._plot.plotItem)
            exporter.export(path)
            QMessageBox.information(self, "Готово", f"График сохранён:\n{path}")
        except Exception as e:
            # Запасной вариант: grab виджета
            try:
                pix: QPixmap = self._plot.grab()
                pix.save(path, "PNG")
                QMessageBox.information(self, "Готово", f"График сохранён:\n{path}")
            except Exception as e2:
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить: {e2}")
