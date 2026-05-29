"""Форма 10: Диалог экспорта.

Выбор формата, диапазона (все / только отфильтрованные видимые),
настройка разделителя для CSV, прогресс-бар.
"""
from __future__ import annotations

import os
from typing import Iterator, Tuple

from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from app.models.log_model import LogTableModel
from app.reports.exporter import EXPORTERS


ExportRow = Tuple[int, str, str, str]


class _ExportThread(QThread):
    """Экспорт в отдельном потоке, чтобы не блокировать UI."""

    finished_ok = pyqtSignal(int)
    error = pyqtSignal(str)
    progress = pyqtSignal(int)

    def __init__(self, rows: list, path: str, fmt: str, delimiter: str = ","):
        super().__init__()
        self._rows = rows
        self._path = path
        self._fmt = fmt
        self._delimiter = delimiter

    def run(self) -> None:
        try:
            exporter = EXPORTERS[self._fmt]
            # Оборачиваем в генератор с прогрессом
            def gen():
                total = len(self._rows)
                for i, r in enumerate(self._rows):
                    if i % 500 == 0:
                        pct = int(i * 100 / max(1, total))
                        self.progress.emit(pct)
                    yield r
                self.progress.emit(100)

            if self._fmt == "CSV":
                count = exporter(gen(), self._path, delimiter=self._delimiter)
            else:
                count = exporter(gen(), self._path)
            self.finished_ok.emit(count)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


class ExportDialog(QDialog):
    """Диалог экспорта отфильтрованных строк."""

    def __init__(self, model: LogTableModel, file_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Экспорт данных")
        self.resize(500, 300)
        self._model = model
        self._source_file = file_path
        self._thread: _ExportThread | None = None

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._combo_format = QComboBox()
        self._combo_format.addItems(list(EXPORTERS.keys()))
        form.addRow("Формат:", self._combo_format)

        # Диапазон экспорта
        self._rb_all = QRadioButton("Все строки, соответствующие фильтру")
        self._rb_all.setChecked(True)
        self._rb_loaded = QRadioButton("Только загруженные (видимые)")
        form.addRow(self._rb_all)
        form.addRow(self._rb_loaded)

        # Разделитель для CSV
        self._delim = QLineEdit(",")
        self._delim.setMaxLength(1)
        self._delim.setFixedWidth(40)
        form.addRow("Разделитель CSV:", self._delim)

        # Путь
        h = QHBoxLayout()
        self._path_edit = QLineEdit()
        default_path = os.path.splitext(os.path.basename(file_path))[0] + "_export"
        self._path_edit.setText(default_path)
        h.addWidget(self._path_edit, stretch=1)
        btn_browse = QPushButton("...")
        btn_browse.clicked.connect(self._browse)
        h.addWidget(btn_browse)
        form.addRow("Файл:", h)

        lay.addLayout(form)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        lay.addWidget(self._progress)

        self._status = QLabel("")
        lay.addWidget(self._status)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._btn_save = box.button(QDialogButtonBox.StandardButton.Save)
        self._btn_save.setText("Экспортировать")
        self._btn_save.clicked.connect(self._start)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


    def _browse(self) -> None:
        fmt = self._combo_format.currentText().lower()
        ext_map = {"csv": "csv", "json": "json", "html": "html", "txt": "txt"}
        ext = ext_map.get(fmt, "txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить как", self._path_edit.text() + "." + ext,
            f"{fmt.upper()} (*.{ext})"
        )
        if path:
            self._path_edit.setText(path)

    def _collect_rows(self) -> list:
        """Собрать строки для экспорта."""
        rows: list = []
        if self._rb_all.isChecked():
            # Докачиваем все строки
            while self._model.canFetchMore():
                self._model.fetchMore()
        count = self._model.rowCount()
        for row in range(count):
            info = self._model.get_line_info(row)
            if not info:
                continue
            line_number, byte_offset, length, level, ts = info
            text = self._model._get_text(line_number, byte_offset, length)  # noqa: SLF001
            rows.append((line_number, level or "", ts or "", text))
        return rows

    def _start(self) -> None:
        path = self._path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Ошибка", "Укажите имя файла")
            return
        fmt = self._combo_format.currentText()
        ext_map = {"CSV": ".csv", "JSON": ".json", "HTML": ".html", "TXT": ".txt"}
        if not path.lower().endswith(ext_map[fmt].lower()):
            path += ext_map[fmt]

        rows = self._collect_rows()
        if not rows:
            QMessageBox.information(self, "Нет данных", "Нет строк для экспорта")
            return

        self._btn_save.setEnabled(False)
        self._status.setText("Экспорт...")
        self._thread = _ExportThread(
            rows, path, fmt, delimiter=self._delim.text() or ","
        )
        self._thread.progress.connect(self._progress.setValue)
        self._thread.finished_ok.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self, count: int) -> None:
        self._progress.setValue(100)
        self._status.setText(f"Готово: экспортировано строк {count}")
        self._btn_save.setEnabled(True)
        QMessageBox.information(
            self, "Готово", f"Экспортировано строк: {count}"
        )
        self.accept()

    def _on_error(self, msg: str) -> None:
        self._btn_save.setEnabled(True)
        self._status.setText("Ошибка")
        QMessageBox.critical(self, "Ошибка экспорта", msg)
