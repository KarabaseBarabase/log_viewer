"""Форма 12: Диалог настроек.

Цветовая схема, размер шрифта, размер батча lazy-загрузки,
папка для отчётов, кнопка очистки кэша SQLite.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.config import DB_PATH, FETCH_BATCH_SIZE


class SettingsDialog(QDialog):
    """Диалог настроек приложения."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.resize(500, 400)

        self._settings = QSettings("log_viewer", "main")

        lay = QVBoxLayout(self)
        form = QFormLayout()

        # Тема
        self._combo_theme = QComboBox()
        self._combo_theme.addItems(["Светлая", "Тёмная"])
        cur_theme = self._settings.value("theme", "Светлая")
        idx = self._combo_theme.findText(str(cur_theme))
        if idx >= 0:
            self._combo_theme.setCurrentIndex(idx)
        form.addRow("Цветовая схема:", self._combo_theme)

        # Шрифт
        self._font_family = QLineEdit(
            self._settings.value("font_family", "Consolas, Menlo, monospace")
        )
        form.addRow("Семейство шрифта:", self._font_family)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 24)
        self._font_size.setValue(int(self._settings.value("font_size", 11)))
        form.addRow("Размер шрифта:", self._font_size)

        # Размер батча
        self._batch_size = QSpinBox()
        self._batch_size.setRange(50, 2000)
        self._batch_size.setValue(
            int(self._settings.value("fetch_batch_size", FETCH_BATCH_SIZE))
        )
        form.addRow("Строк за одну подгрузку:", self._batch_size)

        # Папка для отчётов
        h = QHBoxLayout()
        self._export_dir = QLineEdit(
            self._settings.value("export_dir", os.path.expanduser("~"))
        )
        h.addWidget(self._export_dir, stretch=1)
        btn = QPushButton("...")
        btn.clicked.connect(self._browse_dir)
        h.addWidget(btn)
        form.addRow("Папка для отчётов:", h)

        lay.addLayout(form)

        # Кнопка очистки кэша
        lay.addWidget(QLabel("<b>Кэш:</b>"))
        info = QLabel(f"База данных: {DB_PATH}")
        info.setWordWrap(True)
        lay.addWidget(info)

        btn_clear = QPushButton("Очистить кэш SQLite")
        btn_clear.clicked.connect(self._clear_cache)
        lay.addWidget(btn_clear)

        lay.addStretch()

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self._save)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Выберите папку", self._export_dir.text())
        if d:
            self._export_dir.setText(d)

    def _save(self) -> None:
        self._settings.setValue("theme", self._combo_theme.currentText())
        self._settings.setValue("font_family", self._font_family.text())
        self._settings.setValue("font_size", self._font_size.value())
        self._settings.setValue("fetch_batch_size", self._batch_size.value())
        self._settings.setValue("export_dir", self._export_dir.text())
        self.accept()

    def _clear_cache(self) -> None:
        ret = QMessageBox.question(
            self,
            "Очистка кэша",
            "Удалить кэш индексов? После этого файлы нужно будет проиндексировать заново.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            try:
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                QMessageBox.information(
                    self, "Готово",
                    "Кэш очищен. Перезапустите приложение."
                )
            except Exception as e:
                QMessageBox.warning(self, "Ошибка", str(e))
