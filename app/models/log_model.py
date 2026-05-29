"""Ленивая модель для таблицы логов.

Это реализация паттерна «lazy model» из терминологии Qt:
    - canFetchMore(parent) → True, если есть ещё данные
    - fetchMore(parent)    → дозагружает следующую порцию

В памяти одновременно хранится ограниченное количество строк (окно).
Строки читаются напрямую из файла по byte_offset через seek() — поэтому
модель работает с файлами любого размера (2+ ГБ) без загрузки в память.

Архитектурно:
    Индексы позиций строк (line_number, byte_offset) → лежат в SQLite.
    Текст строки читается из файла по byte_offset, когда он нужен для отображения.
    Кэш прочитанных текстов — LRU с ограничением MAX_LINES_IN_MEMORY.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    QVariant,
)
from PyQt6.QtGui import QBrush, QColor

from app.config import (
    FETCH_BATCH_SIZE,
    LIGHT_THEME,
    MAX_LINES_IN_MEMORY,
)
from app.db.repository import Repository
from app.models.filter_state import FilterState


class LogTableModel(QAbstractTableModel):
    """Ленивая модель таблицы строк лога.

    Колонки:
        0: номер строки
        1: уровень (ERROR/WARN/...)
        2: timestamp
        3: текст строки
    """

    COLUMNS = ("№", "Уровень", "Время", "Сообщение")
    COL_NUMBER, COL_LEVEL, COL_TIMESTAMP, COL_TEXT = range(4)

    def __init__(
        self,
        file_id: int,
        file_path: str,
        repo: Repository,
        parent=None,
    ):
        super().__init__(parent)
        self._file_id = file_id
        self._file_path = file_path
        self._repo = repo
        self._theme = LIGHT_THEME

        # Все индексы строк, удовлетворяющие текущему фильтру
        # (подгружаются из БД при смене фильтра)
        self._indexes: List[tuple] = []  # (line_number, byte_offset, length, level, ts)

        # Сколько строк из _indexes сейчас «показано» модели (для fetchMore)
        self._loaded_count = 0

        # LRU-кэш текстов строк: line_number -> text
        self._text_cache: "OrderedDict[int, str]" = OrderedDict()

        # Текущее состояние фильтра
        self._filter = FilterState()

        # Поисковые подсветки: номера строк, где есть совпадение
        self._search_hits: set[int] = set()

        # Пользовательские паттерны подсветки: список (compiled_regex, QColor).
        # Загружается из БД через reload_patterns(); пересоздаётся при изменении в менеджере.
        self._user_patterns: List[Tuple[re.Pattern, QColor]] = []

        # Открытый файл для быстрого seek() — держим дескриптор всё время
        self._file_handle = open(file_path, "rb")

        # Загружаем паттерны подсветки из БД
        self.reload_patterns()

        # Первичная загрузка индексов под пустой фильтр
        self.apply_filter(self._filter)


    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid():
            return 0
        return self._loaded_count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: E501
        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.COLUMNS):
            return self.COLUMNS[section]
        return QVariant()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()
        row = index.row()
        if row < 0 or row >= self._loaded_count:
            return QVariant()

        line_number, byte_offset, length, level, ts = self._indexes[row]

        # Отображение
        if role == Qt.ItemDataRole.DisplayRole:
            col = index.column()
            if col == self.COL_NUMBER:
                return line_number
            if col == self.COL_LEVEL:
                return level or ""
            if col == self.COL_TIMESTAMP:
                return ts or ""
            if col == self.COL_TEXT:
                return self._get_text(line_number, byte_offset, length)
            return ""

        # Фон строки. Приоритет (сверху вниз):
        #   1) подсветка поиска (жёлтый);
        #   2) совпадение с пользовательским regex-паттерном;
        #   3) подсветка по уровню (ERROR/WARN/...).
        if role == Qt.ItemDataRole.BackgroundRole:
            if line_number in self._search_hits:
                return QBrush(QColor("#FFFF80"))
            # Пользовательские паттерны — ищем в тексте строки
            if self._user_patterns:
                text = self._get_text(line_number, byte_offset, length)
                for compiled, color in self._user_patterns:
                    if compiled.search(text):
                        return QBrush(color)
            if level and level in self._theme:
                return QBrush(QColor(self._theme[level]))

        # Подсказка: полный текст строки при наведении
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._get_text(line_number, byte_offset, length)

        return QVariant()

    # Ленивая модель — ключевые методы

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: B008
        if parent.isValid():
            return False
        return self._loaded_count < len(self._indexes)

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:  # noqa: B008
        """Подгрузить следующие FETCH_BATCH_SIZE строк."""
        if parent.isValid():
            return
        remaining = len(self._indexes) - self._loaded_count
        to_fetch = min(FETCH_BATCH_SIZE, remaining)
        if to_fetch <= 0:
            return

        self.beginInsertRows(
            QModelIndex(),
            self._loaded_count,
            self._loaded_count + to_fetch - 1,
        )
        self._loaded_count += to_fetch
        self.endInsertRows()


    def apply_filter(self, f: FilterState) -> None:
        """Применить новый фильтр — перезагрузить список индексов из БД."""
        self._filter = f
        self.beginResetModel()
        levels = list(f.levels) if f.levels else None
        rows = self._repo.get_indexes(self._file_id, levels=levels)
        # Если задан текстовый фильтр — применяем его на уровне Python
        # (БД не хранит текст строк, только индексы)
        if f.text_pattern:
            rows = self._filter_by_text(rows, f)
        self._indexes = [
            (r["line_number"], r["byte_offset"], r["line_length"], r["level"], r["timestamp"])
            for r in rows
        ]
        self._loaded_count = 0
        self.endResetModel()
        # Первая порция подгружается сразу
        self.fetchMore()

    def _filter_by_text(self, rows, f: FilterState):
        """Пропустить через текстовый фильтр. Читает строки из файла."""
        import re as _re
        if f.is_regex:
            try:
                pat = _re.compile(f.text_pattern, 0 if f.case_sensitive else _re.IGNORECASE)
            except _re.error:
                return rows  # битая регулярка — фильтр игнорируется
            matches = lambda s: bool(pat.search(s))  # noqa: E731
        else:
            needle = f.text_pattern if f.case_sensitive else f.text_pattern.lower()
            matches = (
                (lambda s: needle in s)
                if f.case_sensitive
                else (lambda s: needle in s.lower())
            )

        result = []
        for r in rows:
            text = self._get_text(r["line_number"], r["byte_offset"], r["line_length"])
            if matches(text):
                result.append(r)
        return result


    def set_search_hits(self, line_numbers: set[int]) -> None:
        """Установить подсветку поиска — множество номеров строк."""
        self._search_hits = line_numbers
        if self._loaded_count > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._loaded_count - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.BackgroundRole],
            )

    def clear_search_hits(self) -> None:
        self.set_search_hits(set())


    def set_theme(self, theme: dict) -> None:
        self._theme = theme
        if self._loaded_count > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._loaded_count - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.BackgroundRole],
            )

    def reload_patterns(self) -> None:
        """Перечитать пользовательские паттерны подсветки из БД.

        Вызывается при создании модели и после изменения паттернов в менеджере.
        Невалидные regex молча пропускаются.
        """
        self._user_patterns = []
        try:
            rows = self._repo.list_patterns()
        except Exception:
            rows = []

        for row in rows:
            # sqlite3.Row не поддерживает .get(), читаем напрямую и через try
            try:
                pattern_text = row["pattern"]
                color_text = row["color"]
            except (IndexError, KeyError):
                continue
            try:
                compiled = re.compile(pattern_text)
            except re.error:
                continue
            self._user_patterns.append((compiled, QColor(color_text)))

        # Перерисуем видимые строки с учётом новых паттернов
        if self._loaded_count > 0:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(self._loaded_count - 1, self.columnCount() - 1),
                [Qt.ItemDataRole.BackgroundRole],
            )

    def line_number_at(self, row: int) -> int:
        """Номер строки в файле для строки таблицы."""
        return self._indexes[row][0]

    def text_at(self, row: int) -> str:
        """Текст сообщения для строки таблицы (использует кэш)."""
        line_number, byte_offset, length, _, _ = self._indexes[row]
        return self._get_text(line_number, byte_offset, length)

    def row_tuple_at(self, row: int) -> tuple:
        """Кортеж (номер, уровень, время, текст) для строки таблицы."""
        line_number, byte_offset, length, level, ts = self._indexes[row]
        text = self._get_text(line_number, byte_offset, length)
        return (line_number, level, ts, text)

    def find_error_row(self, from_row: int, direction: int) -> Optional[int]:
        """Ищет ближайшую строку с уровнем ERROR в нужном направлении.

        direction=+1 — вперёд (следующая ошибка), -1 — назад (предыдущая).
        Возвращает индекс строки в таблице или None если ошибок нет.
        """
        if not self._indexes:
            return None
        n = len(self._indexes)
        step = 1 if direction >= 0 else -1
        i = from_row + step
        while 0 <= i < n:
            if self._indexes[i][3] == "ERROR":
                # Если строка ещё не в видимом окне модели — догружаем
                while self._loaded_count <= i:
                    self.fetchMore()
                return i
            i += step
        return None

    def _get_text(self, line_number: int, byte_offset: int, length: int) -> str:
        """Прочитать текст строки по byte_offset с LRU-кэшированием."""
        if line_number in self._text_cache:
            # Обновляем позицию в LRU
            self._text_cache.move_to_end(line_number)
            return self._text_cache[line_number]

        try:
            self._file_handle.seek(byte_offset)
            raw = self._file_handle.read(length)
            text = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        except Exception as e:  # noqa: BLE001
            text = f"<ошибка чтения строки: {e}>"

        self._text_cache[line_number] = text
        # Ограничиваем размер кэша
        while len(self._text_cache) > MAX_LINES_IN_MEMORY:
            self._text_cache.popitem(last=False)

        return text

    def total_matched(self) -> int:
        """Сколько всего строк удовлетворяет текущему фильтру."""
        return len(self._indexes)

    def get_line_info(self, row: int) -> Optional[tuple]:
        """Получить сырой кортеж индекса для строки (для дерева/внешних вызовов)."""
        if 0 <= row < len(self._indexes):
            return self._indexes[row]
        return None

    def find_row_by_line_number(self, line_number: int) -> int:
        """Найти индекс строки в модели по её номеру в файле (для перехода от дерева)."""
        # Линейный поиск — индексов может быть мало (sparse), это ок.
        # Для полной загрузки использовать бинарный поиск.
        for i, idx in enumerate(self._indexes):
            if idx[0] == line_number:
                return i
            if idx[0] > line_number:
                return max(0, i - 1)
        return max(0, len(self._indexes) - 1)

    def close(self) -> None:
        """Закрыть файловый дескриптор — вызывать при смене файла."""
        try:
            self._file_handle.close()
        except Exception:
            pass
