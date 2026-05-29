"""Форма 5: Панель фильтрации.

Над просмотрщиком. Включает:
    - Поле ввода текстового фильтра
    - Чекбоксы уровней
    - Галочку «регулярное выражение»
    - Галочку «учитывать регистр»
    - Кнопки «Применить», «Сбросить», «Сохранить фильтр»
"""
from __future__ import annotations

from typing import FrozenSet

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import LEVELS
from app.db.repository import Repository
from app.models.filter_state import FilterState


class FilterPanel(QWidget):
    """Панель фильтрации над просмотрщиком логов."""

    filterChanged = pyqtSignal(FilterState)

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self._repo = repo

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Фильтр:"))

        self._text = QLineEdit()
        self._text.setPlaceholderText("Текст или регулярное выражение...")
        self._text.returnPressed.connect(self._apply)
        row1.addWidget(self._text, stretch=2)

        self._cb_regex = QCheckBox("regex")
        row1.addWidget(self._cb_regex)

        self._cb_case = QCheckBox("Aa")
        self._cb_case.setToolTip("Учитывать регистр")
        row1.addWidget(self._cb_case)

        # Сохранённые фильтры
        self._saved_combo = QComboBox()
        self._saved_combo.setMinimumWidth(150)
        self._saved_combo.addItem("— сохранённые —")
        self._refresh_saved()
        self._saved_combo.activated.connect(self._load_saved)
        row1.addWidget(self._saved_combo)

        outer.addLayout(row1)

        # Уровни
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Уровни:"))
        self._level_checks: dict[str, QCheckBox] = {}
        for level in LEVELS:
            cb = QCheckBox(level)
            self._level_checks[level] = cb
            row2.addWidget(cb)

        row2.addStretch()

        self._btn_apply = QPushButton("Применить")
        self._btn_apply.clicked.connect(self._apply)
        row2.addWidget(self._btn_apply)

        self._btn_reset = QPushButton("Сбросить")
        self._btn_reset.clicked.connect(self.reset)
        row2.addWidget(self._btn_reset)

        self._btn_save = QPushButton("Сохранить...")
        self._btn_save.clicked.connect(self._save_current)
        row2.addWidget(self._btn_save)

        outer.addLayout(row2)


    def reset(self) -> None:
        self._text.clear()
        self._cb_regex.setChecked(False)
        self._cb_case.setChecked(False)
        for cb in self._level_checks.values():
            cb.setChecked(False)
        self.filterChanged.emit(FilterState())

    def current_filter(self) -> FilterState:
        levels: FrozenSet[str] = frozenset(
            lvl for lvl, cb in self._level_checks.items() if cb.isChecked()
        )
        return FilterState(
            text_pattern=self._text.text().strip(),
            is_regex=self._cb_regex.isChecked(),
            case_sensitive=self._cb_case.isChecked(),
            levels=levels,
        )


    def _apply(self) -> None:
        self.filterChanged.emit(self.current_filter())

    def _save_current(self) -> None:
        f = self.current_filter()
        name, ok = QInputDialog.getText(self, "Сохранить фильтр", "Название:")
        if not ok or not name.strip():
            return
        self._repo.save_filter(
            name.strip(),
            f.text_pattern,
            f.is_regex,
            ",".join(sorted(f.levels)),
        )
        self._refresh_saved()

    def _refresh_saved(self) -> None:
        self._saved_combo.blockSignals(True)
        self._saved_combo.clear()
        self._saved_combo.addItem("— сохранённые —")
        for row in self._repo.list_filters():
            self._saved_combo.addItem(row["name"], row["id"])
        self._saved_combo.blockSignals(False)

    def _load_saved(self, i: int) -> None:
        if i <= 0:
            return
        filter_id = self._saved_combo.itemData(i)
        for row in self._repo.list_filters():
            if row["id"] == filter_id:
                self._text.setText(row["pattern"] or "")
                self._cb_regex.setChecked(bool(row["is_regex"]))
                levels = set((row["levels"] or "").split(","))
                for lvl, cb in self._level_checks.items():
                    cb.setChecked(lvl in levels)
                self._apply()
                break
