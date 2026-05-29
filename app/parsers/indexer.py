"""Фоновая индексация лог-файла.

Читает файл блоками по 1 МБ, находит позиции (byte_offset) каждой строки,
парсит уровень и timestamp, батчами пишет в SQLite.

НЕ загружает весь файл в память — это и есть «ленивая» часть.
При 2 ГБ файле используется ~10 МБ RAM (на буфер + батч записи в БД).

Сигналы:
    progress(percent, lines_indexed)  — прогресс индексации
    finished(file_id, total_lines)     — успешное завершение
    error(message)                     — ошибка при индексации
"""
from __future__ import annotations

import os
from typing import List, Tuple

from PyQt6.QtCore import QThread, pyqtSignal

from app.config import INDEX_CHUNK_SIZE, SPARSE_INDEX_STEP
from app.parsers.log_parser import detect_level, detect_timestamp
from app.db.repository import Repository


# Батч для вставки в БД: (line_number, byte_offset, line_length, level, timestamp)
IndexBatch = List[Tuple[int, int, int, str | None, str | None]]


class IndexerThread(QThread):
    """Фоновый поток индексации.

    Использование:
        t = IndexerThread(path, repo)
        t.progress.connect(on_progress)
        t.finished_ok.connect(on_done)
        t.error.connect(on_error)
        t.start()
    """

    progress = pyqtSignal(int, int)      # (percent 0..100, lines indexed)
    finished_ok = pyqtSignal(int, int)   # (file_id, total_lines)
    error = pyqtSignal(str)
    cancelled = pyqtSignal()             # Пользователь нажал Отмена

    # Размер батча для записи в БД (строк за одну транзакцию)
    BATCH_SIZE = 5000

    def __init__(self, file_path: str, repo: Repository, parent=None):
        super().__init__(parent)
        self._path = file_path
        self._repo = repo
        self._cancelled = False

    def cancel(self) -> None:
        """Пользователь отменил индексацию."""
        self._cancelled = True

    def run(self) -> None:
        try:
            self._do_index()
        except Exception as e:  # noqa: BLE001 — нужно поймать всё и показать в UI
            self.error.emit(f"Ошибка индексации: {e}")

    def _do_index(self) -> None:
        path = self._path
        if not os.path.exists(path):
            self.error.emit(f"Файл не найден: {path}")
            return

        file_size = os.path.getsize(path)
        if file_size == 0:
            self.error.emit("Файл пустой")
            return

        # Создаём/обновляем запись о файле
        file_id = self._repo.upsert_file(path, file_size)
        # Очищаем старые индексы для этого файла (переиндексируем)
        self._repo.clear_indexes(file_id)

        batch: IndexBatch = []
        line_number = 0
        byte_offset = 0
        bytes_read = 0

        # Читаем построчно через бинарный режим — контролируем byte_offset
        with open(path, "rb") as f:
            for raw_line in f:
                if self._cancelled:
                    # Сбрасываем то что уже накопили — индексы частично пригодны,
                    # но при следующей индексации этого же файла будут очищены через
                    # clear_indexes() в начале нового _do_index.
                    try:
                        self._repo.flush_indexes(batch, file_id)
                    except Exception:
                        pass
                    self.cancelled.emit()
                    return

                line_number += 1
                line_length = len(raw_line)

                # Декодируем только для парсинга — сохраняем text только для sparse-индекса
                try:
                    text = raw_line.decode("utf-8", errors="replace")
                except Exception:
                    text = raw_line.decode("latin-1", errors="replace")

                # Убираем перевод строки
                text = text.rstrip("\r\n")

                level = detect_level(text)
                timestamp = detect_timestamp(text)

                # Sparse-индекс: сохраняем каждую N-ю строку + ВСЕ ERROR/WARN
                # Это принципиально — если хранить каждую строку, БД раздуется.
                is_important = level in ("ERROR", "WARN")
                is_sparse = (line_number % SPARSE_INDEX_STEP == 0)

                if is_important or is_sparse or line_number == 1:
                    batch.append((line_number, byte_offset, line_length, level, timestamp))

                byte_offset += line_length
                bytes_read += line_length

                # Периодически сбрасываем батч и шлём прогресс
                if len(batch) >= self.BATCH_SIZE:
                    self._repo.flush_indexes(batch, file_id)
                    batch = []
                    percent = int(bytes_read * 100 / file_size)
                    self.progress.emit(percent, line_number)

        # Финальный сброс батча
        if batch:
            self._repo.flush_indexes(batch, file_id)

        # Обновляем total_lines в БД
        self._repo.update_file_stats(file_id, total_lines=line_number)

        # Сообщаем UI
        self.finished_ok.emit(file_id, line_number)
