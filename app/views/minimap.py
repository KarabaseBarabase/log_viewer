"""Мини-карта файла: полоса с подсветкой ERROR/WARN по всей длине.

Рисуется на QWidget через paintEvent. Клик по полосе — сигнал positionClicked
с долей позиции (0.0 — верх файла, 1.0 — низ).
"""
from __future__ import annotations

from typing import List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class MinimapWidget(QWidget):
    """Вертикальная heatmap-полоса."""

    positionClicked = pyqtSignal(float)  # 0.0..1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: List[int] = []
        self.setMinimumHeight(100)
        self.setToolTip("Мини-карта файла. Красный — плотность ошибок.\nКлик — перейти к позиции.")

    def set_data(self, data: List[int]) -> None:
        self._data = list(data)
        self.update()

    def paintEvent(self, e) -> None:  # type: ignore[override]
        p = QPainter(self)
        w = self.width()
        h = self.height()

        # Фон
        p.fillRect(self.rect(), QColor(230, 230, 230))

        if not self._data:
            p.setPen(QColor(150, 150, 150))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "—")
            return

        max_val = max(self._data) if self._data else 1
        if max_val == 0:
            return

        n = len(self._data)
        bucket_h = h / n
        for i, v in enumerate(self._data):
            if v == 0:
                continue
            # Цвет: от жёлтого к красному в зависимости от плотности
            intensity = v / max_val
            # Интерполяция жёлтый (255,230,100) → красный (220,30,30)
            r = int(255 - (255 - 220) * intensity)
            g = int(230 - (230 - 30) * intensity)
            b = int(100 - (100 - 30) * intensity)
            p.fillRect(
                0,
                int(i * bucket_h),
                w,
                int(bucket_h) + 1,
                QColor(r, g, b),
            )

    def mousePressEvent(self, e) -> None:  # type: ignore[override]
        if self.height() <= 0:
            return
        fraction = max(0.0, min(1.0, e.position().y() / self.height()))
        self.positionClicked.emit(fraction)
