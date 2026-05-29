"""Форма 9: Менеджер пользовательских паттернов подсветки.

Список regex с цветом. Можно добавлять, удалять, тестировать на примере.
"""
from __future__ import annotations

import re
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.db.repository import Repository


# Примеры паттернов с пояснениями. Показываются в форме как справка.
PATTERN_EXAMPLES = [
    ("Exception",                 "Простая подстрока: совпадёт со словом «Exception» в любом месте строки."),
    ("Exception|Error",           "Альтернатива: совпадёт с «Exception» ИЛИ «Error»."),
    ("Exception.*timeout",        ".* — любые символы между двумя словами (на одной строке)."),
    ("^ERROR",                    "^ — привязка к началу строки. Совпадёт только если строка начинается с ERROR."),
    ("timeout$",                  "$ — привязка к концу строки."),
    ("user_id=\\d+",              "\\d+ — одна или более цифр. Найдёт user_id=123, user_id=4567 и т.п."),
    ("\\b\\w+@\\w+\\.\\w+\\b",    "Email-подобный шаблон: слово@слово.слово (\\b — граница слова)."),
    ("HTTP 5\\d{2}",              "5\\d{2} — 5 и две цифры. Найдёт HTTP 500, 502, 503 и т.д."),
    ("\\[(ERROR|WARN)\\]",        "Скобки экранируем, внутри — альтернатива. Найдёт [ERROR] или [WARN]."),
    ("(?i)database",              "(?i) — без учёта регистра. Найдёт database, Database, DATABASE."),
]


class PatternManagerDialog(QDialog):
    """Редактирование паттернов подсветки."""

    def __init__(self, repo: Repository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Менеджер паттернов подсветки")
        self.resize(900, 650)
        self._repo = repo
        self._current_color = "#FFD700"

        lay = QVBoxLayout(self)

        lay.addWidget(QLabel(
            "Пользовательские regex-паттерны для подсветки строк. "
            "Каждый паттерн — отдельная запись в таблице ниже."
        ))

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Паттерн", "Цвет", "Действия"])
        # Колонка с паттерном тянется, цвет и действия — по содержимому
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._table, stretch=2)

        # Форма добавления
        lay.addWidget(QLabel(
            "<b>Добавить паттерн.</b> Введите ОДНО регулярное выражение, "
            "выберите цвет кнопкой справа и нажмите «Добавить». "
            "Чтобы подсвечивать несколько слов разными цветами — добавьте каждое отдельной записью."
        ))
        form = QHBoxLayout()
        form.addWidget(QLabel("Regex:"))
        self._pat_edit = QLineEdit()
        self._pat_edit.setPlaceholderText("например:  Exception   или   timeout|refused")
        form.addWidget(self._pat_edit, stretch=2)

        self._color_btn = QPushButton("Цвет")
        self._color_btn.clicked.connect(self._pick_color)
        self._apply_color_preview()
        form.addWidget(self._color_btn)

        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self._add)
        form.addWidget(btn_add)

        btn_help = QPushButton("Примеры…")
        btn_help.clicked.connect(self._show_help)
        form.addWidget(btn_help)
        lay.addLayout(form)

        # Тестирование
        lay.addWidget(QLabel("<b>Тест на примере:</b>"))
        self._sample = QPlainTextEdit()
        self._sample.setPlaceholderText(
            "Вставьте сюда пример строки, чтобы проверить соответствие…"
        )
        self._sample.setFixedHeight(60)
        lay.addWidget(self._sample)

        self._test_label = QLabel("")
        lay.addWidget(self._test_label)

        btn_test = QPushButton("Проверить")
        btn_test.clicked.connect(self._test)
        lay.addWidget(btn_test)

        # Краткая справка по основным метасимволам — всегда видна
        hint = QGroupBox("Шпаргалка по синтаксису")
        hint_lay = QVBoxLayout(hint)
        hint_text = QLabel(
            "<table cellpadding='3'>"
            "<tr><td><code>текст</code></td><td>подстрока</td>"
            "<td><code>a|b</code></td><td>a или b</td></tr>"
            "<tr><td><code>.</code></td><td>любой символ</td>"
            "<td><code>.*</code></td><td>любые символы</td></tr>"
            "<tr><td><code>^</code></td><td>начало строки</td>"
            "<td><code>$</code></td><td>конец строки</td></tr>"
            "<tr><td><code>\\d</code></td><td>цифра</td>"
            "<td><code>\\d+</code></td><td>одна и более цифр</td></tr>"
            "<tr><td><code>\\w</code></td><td>буква/цифра/_</td>"
            "<td><code>\\b</code></td><td>граница слова</td></tr>"
            "<tr><td><code>[abc]</code></td><td>один из a, b, c</td>"
            "<td><code>(?i)</code></td><td>без учёта регистра</td></tr>"
            "</table>"
        )
        hint_text.setTextFormat(Qt.TextFormat.RichText)
        hint_lay.addWidget(hint_text)
        lay.addWidget(hint)

        # Кнопки
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.accept)
        box.accepted.connect(self.accept)
        lay.addWidget(box)

        self._refresh_table()

    def _refresh_table(self) -> None:
        patterns = self._repo.list_patterns()
        self._table.setRowCount(len(patterns))
        for i, p in enumerate(patterns):
            self._table.setItem(i, 0, QTableWidgetItem(p["pattern"]))
            color_item = QTableWidgetItem(p["color"])
            color_item.setBackground(QColor(p["color"]))
            self._table.setItem(i, 1, color_item)

            btn = QPushButton("Удалить")
            btn.clicked.connect(lambda _=False, pid=p["id"]: self._delete(pid))
            self._table.setCellWidget(i, 2, btn)

    def _apply_color_preview(self) -> None:
        self._color_btn.setStyleSheet(
            f"background: {self._current_color}; color: #000; padding: 4px 12px;"
        )

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._current_color), self, "Выберите цвет")
        if color.isValid():
            self._current_color = color.name()
            self._apply_color_preview()

    def _add(self) -> None:
        pat = self._pat_edit.text().strip()
        if not pat:
            return
        # Проверяем валидность regex до сохранения, чтобы не записать в БД мусор
        try:
            re.compile(pat)
        except re.error as e:
            QMessageBox.warning(self, "Невалидная регулярка", str(e))
            return
        self._repo.add_pattern(pat, self._current_color, is_regex=True)
        self._pat_edit.clear()
        self._refresh_table()

    def _delete(self, pattern_id: int) -> None:
        self._repo.delete_pattern(pattern_id)
        self._refresh_table()

    def _test(self) -> None:
        sample = self._sample.toPlainText()
        pat_text = self._pat_edit.text().strip()
        if not pat_text or not sample:
            self._test_label.setText("Введите regex и пример")
            return
        try:
            m = re.search(pat_text, sample)
        except re.error as e:
            self._test_label.setText(f"<span style='color:red'>Ошибка regex: {e}</span>")
            return
        if m:
            self._test_label.setText(
                f"<span style='color:green'>✓ Совпадение: «{m.group(0)}»</span>"
            )
        else:
            self._test_label.setText(
                "<span style='color:#c00'>✗ Нет совпадения</span>"
            )

    def _show_help(self) -> None:
        """Показать диалог с подробными примерами паттернов."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Примеры паттернов")
        msg.setTextFormat(Qt.TextFormat.RichText)
        rows = "".join(
            f"<tr><td valign='top'><code><b>{pat}</b></code></td>"
            f"<td>{desc}</td></tr>"
            for pat, desc in PATTERN_EXAMPLES
        )
        msg.setText(
            "<p>Используется синтаксис регулярных выражений Python (модуль <code>re</code>).</p>"
            "<table cellpadding='6'>" + rows + "</table>"
        )
        msg.exec()
