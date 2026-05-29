"""Форма 11: Статистика файла.

Общий размер, количество строк, распределение по уровням (круговая
диаграмма), временной диапазон, кодировка.
"""
from __future__ import annotations

import os

import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.db.repository import Repository


class _PieChartWidget(QWidget):
    """Примитивная круговая диаграмма на paintEvent (без доп. зависимостей)."""

    COLORS = {
        "ERROR": QColor("#D04040"),
        "WARN":  QColor("#E0B030"),
        "INFO":  QColor("#4090D0"),
        "DEBUG": QColor("#808080"),
        "TRACE": QColor("#A0A0A0"),
    }

    def __init__(self, data: dict[str, int], parent=None):
        super().__init__(parent)
        self._data = data
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, e) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._data or sum(self._data.values()) == 0:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Нет данных")
            return

        total = sum(self._data.values())
        rect = self.rect().adjusted(20, 20, -140, -20)
        # Делаем квадратом
        side = min(rect.width(), rect.height())
        rect.setWidth(side)
        rect.setHeight(side)

        start_angle = 90 * 16  # В Qt: 1/16 градуса; начинаем сверху
        for level, value in self._data.items():
            span = int(-value / total * 360 * 16)
            color = self.COLORS.get(level, QColor("#888"))
            p.setBrush(color)
            p.setPen(QPen(Qt.GlobalColor.white, 2))
            p.drawPie(rect, start_angle, span)
            start_angle += span

        # Легенда справа
        legend_x = rect.right() + 20
        y = rect.top() + 10
        p.setPen(Qt.GlobalColor.black)
        for level, value in self._data.items():
            color = self.COLORS.get(level, QColor("#888"))
            p.setBrush(color)
            p.drawRect(legend_x, y, 14, 14)
            pct = value * 100 / total
            p.drawText(legend_x + 22, y + 12, f"{level}: {value} ({pct:.1f}%)")
            y += 22


class StatisticsDialog(QDialog):
    """Диалог статистики файла."""

    def __init__(self, file_id: int, repo: Repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Статистика файла")
        self.resize(900, 500)

        file_row = repo.get_file(file_id)
        counts = repo.count_by_level(file_id)

        lay = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая часть: форма с данными
        left = QWidget()
        form = QFormLayout(left)
        if file_row:
            size_mb = file_row["file_size"] / (1024 * 1024)
            form.addRow("Путь:", QLabel(file_row["path"]))
            form.addRow("Размер:", QLabel(
                f"{file_row['file_size']:,} байт ({size_mb:.2f} МБ)".replace(",", " ")
            ))
            form.addRow("Количество строк:", QLabel(
                f"{file_row['total_lines']:,}".replace(",", " ")
            ))
            form.addRow("Первая метка времени:", QLabel(
                file_row["first_timestamp"] or "—"
            ))
            form.addRow("Последняя метка времени:", QLabel(
                file_row["last_timestamp"] or "—"
            ))
            form.addRow("Последнее открытие:", QLabel(
                str(file_row["last_opened"])
            ))

        # Распределение по уровням в виде таблицы
        form.addRow(QLabel("<b>Распределение по уровням:</b>"))
        total = sum(counts.values()) or 1
        for level in ("ERROR", "WARN", "INFO", "DEBUG", "TRACE"):
            cnt = counts.get(level, 0)
            pct = cnt * 100 / total
            form.addRow(level + ":", QLabel(f"{cnt:,}  ({pct:.2f}%)".replace(",", " ")))

        # Определяем кодировку (упрощённо)
        encoding = "UTF-8 (предположительно)"
        if file_row:
            try:
                with open(file_row["path"], "rb") as f:
                    head = f.read(4096)
                if head.startswith(b"\xef\xbb\xbf"):
                    encoding = "UTF-8 with BOM"
                elif b"\x00" in head:
                    encoding = "UTF-16 (предположительно)"
            except Exception:
                encoding = "неизвестна"
        form.addRow("Кодировка:", QLabel(encoding))

        splitter.addWidget(left)

        # Правая часть: круговая диаграмма
        pie = _PieChartWidget(counts)
        splitter.addWidget(pie)
        splitter.setSizes([400, 500])

        lay.addWidget(splitter, stretch=1)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.accept)
        box.accepted.connect(self.accept)
        lay.addWidget(box)
