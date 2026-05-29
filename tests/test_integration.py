"""Integration smoke test: проверяет полный пайплайн индексации без GUI.

Не использует PyQt для чтения — воспроизводит логику IndexerThread напрямую,
чтобы убедиться, что:
    1) БД создаётся корректно
    2) Индексы пишутся
    3) Репозиторий возвращает правильные данные для отчётов

Запуск: python -m unittest tests.test_integration
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from app.config import SPARSE_INDEX_STEP
from app.db.database import init_db, get_connection
from app.db.repository import Repository
from app.parsers.log_parser import detect_level, detect_timestamp


class TestPipeline(unittest.TestCase):
    """Проверяем полный пайплайн: файл → индекс → репорты."""

    def setUp(self) -> None:
        self._tmp_db = Path(tempfile.mktemp(suffix=".db"))
        init_db(self._tmp_db)
        self._conn = get_connection(self._tmp_db)
        self._repo = Repository(self._conn)

        self._tmp_log = Path(tempfile.mktemp(suffix=".log"))
        with open(self._tmp_log, "w", encoding="utf-8") as f:
            f.write("2025-03-15 10:00:00 [INFO] Starting application\n")
            f.write("2025-03-15 10:00:01 [INFO] Loading config from /etc/app.conf\n")
            f.write("2025-03-15 10:00:02 [DEBUG] Thread-1 acquired lock\n")
            f.write("2025-03-15 10:00:03 [WARN] Slow query: 1500ms\n")
            f.write("2025-03-15 10:00:04 [ERROR] Failed to connect to database\n")
            f.write("2025-03-15 10:00:05 [INFO] Retry attempt 1\n")
            f.write("2025-03-15 10:00:06 [ERROR] Timeout after 5000ms\n")
            f.write("2025-03-15 10:00:07 [WARN] Rate limit approaching\n")
            f.write("2025-03-15 10:00:08 [INFO] Recovered\n")
            f.write("2025-03-15 10:00:09 [INFO] Shutting down\n")

    def tearDown(self) -> None:
        self._conn.close()
        if self._tmp_db.exists():
            self._tmp_db.unlink()
        if self._tmp_log.exists():
            self._tmp_log.unlink()

    def _index_file(self) -> int:
        """Повторяет логику IndexerThread.run() без QThread."""
        file_size = os.path.getsize(self._tmp_log)
        file_id = self._repo.upsert_file(str(self._tmp_log), file_size)
        self._repo.clear_indexes(file_id)

        batch = []
        line_number = 0
        byte_offset = 0

        with open(self._tmp_log, "rb") as f:
            for raw_line in f:
                line_number += 1
                line_length = len(raw_line)
                text = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

                level = detect_level(text)
                timestamp = detect_timestamp(text)

                is_important = level in ("ERROR", "WARN")
                is_sparse = (line_number % SPARSE_INDEX_STEP == 0)

                if is_important or is_sparse or line_number == 1:
                    batch.append((line_number, byte_offset, line_length, level, timestamp))

                byte_offset += line_length

        self._repo.flush_indexes(batch, file_id)
        self._repo.update_file_stats(file_id, total_lines=line_number)
        return file_id

    def test_file_registered(self):
        file_id = self._index_file()
        row = self._repo.get_file(file_id)
        self.assertIsNotNone(row)
        self.assertEqual(row["total_lines"], 10)

    def test_indexes_written(self):
        file_id = self._index_file()
        indexes = self._repo.get_indexes(file_id)
        # Первая строка + 2 ERROR + 2 WARN = минимум 5
        self.assertGreaterEqual(len(indexes), 5)
        line_numbers = [i["line_number"] for i in indexes]
        self.assertIn(1, line_numbers)
        self.assertIn(4, line_numbers)
        self.assertIn(5, line_numbers)
        self.assertIn(7, line_numbers)
        self.assertIn(8, line_numbers)

    def test_level_counts(self):
        file_id = self._index_file()
        counts = self._repo.count_by_level(file_id)
        self.assertEqual(counts.get("ERROR"), 2)
        self.assertEqual(counts.get("WARN"), 2)

    def test_filter_by_level(self):
        file_id = self._index_file()
        errors = self._repo.get_indexes(file_id, levels=["ERROR"])
        self.assertEqual(len(errors), 2)
        for e in errors:
            self.assertEqual(e["level"], "ERROR")

    def test_heatmap(self):
        file_id = self._index_file()
        heatmap = self._repo.get_heatmap(file_id, buckets=10)
        self.assertEqual(len(heatmap), 10)
        self.assertGreater(sum(heatmap), 0)

    def test_errors_per_hour(self):
        file_id = self._index_file()
        ephs = self._repo.errors_per_hour(file_id)
        total = sum(c for _, c in ephs)
        self.assertEqual(total, 2)

    def test_read_line_by_offset(self):
        """Ключевая проверка: можем прочитать строку по byte_offset."""
        file_id = self._index_file()
        indexes = self._repo.get_indexes(file_id)
        first = [i for i in indexes if i["line_number"] == 1][0]

        with open(self._tmp_log, "rb") as f:
            f.seek(first["byte_offset"])
            raw = f.read(first["line_length"])
            text = raw.decode("utf-8").rstrip("\r\n")

        self.assertIn("Starting application", text)


if __name__ == "__main__":
    unittest.main()
