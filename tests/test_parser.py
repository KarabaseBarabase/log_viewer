"""Юнит-тесты парсера логов.

Запуск:
    python -m unittest tests.test_parser
"""
from __future__ import annotations

import unittest
from datetime import datetime

from app.parsers.log_parser import (
    detect_level,
    detect_timestamp,
    parse_line,
    timestamp_to_datetime,
)


class TestDetectLevel(unittest.TestCase):
    """Определение уровня логирования по строке."""

    def test_error_explicit(self):
        self.assertEqual(detect_level("2025-03-15 10:00 [ERROR] Connection refused"), "ERROR")

    def test_error_via_fatal(self):
        self.assertEqual(detect_level("FATAL: disk full"), "ERROR")

    def test_error_via_critical(self):
        self.assertEqual(detect_level("CRITICAL failure"), "ERROR")

    def test_warn_explicit(self):
        self.assertEqual(detect_level("2025-03-15 [WARN] slow query"), "WARN")

    def test_warn_warning(self):
        self.assertEqual(detect_level("WARNING: retry attempt"), "WARN")

    def test_info(self):
        self.assertEqual(detect_level("INFO: user logged in"), "INFO")

    def test_debug(self):
        self.assertEqual(detect_level("DEBUG entering function"), "DEBUG")

    def test_trace(self):
        self.assertEqual(detect_level("TRACE: var=42"), "TRACE")

    def test_no_level(self):
        self.assertIsNone(detect_level("just some text without any level"))

    def test_error_has_priority_over_info(self):
        """ERROR ищется раньше INFO по порядку LEVEL_PATTERNS."""
        self.assertEqual(detect_level("ERROR and some INFO mention"), "ERROR")

    def test_case_insensitive(self):
        self.assertEqual(detect_level("error happened"), "ERROR")
        self.assertEqual(detect_level("Error happened"), "ERROR")

    def test_word_boundary(self):
        """terrors не должно считаться за ERROR."""
        result = detect_level("had some terrors last night")
        self.assertIsNone(result)


class TestDetectTimestamp(unittest.TestCase):
    """Извлечение timestamp из строки."""

    def test_iso_with_ms(self):
        ts = detect_timestamp("2025-03-15T10:23:45.123Z some message")
        self.assertEqual(ts, "2025-03-15T10:23:45.123Z")

    def test_iso_space(self):
        ts = detect_timestamp("2025-03-15 10:23:45.123 ERROR blah")
        self.assertEqual(ts, "2025-03-15 10:23:45.123")

    def test_iso_without_ms(self):
        ts = detect_timestamp("2025-03-15 10:23:45 INFO ok")
        self.assertEqual(ts, "2025-03-15 10:23:45")

    def test_syslog_format(self):
        ts = detect_timestamp("Mar 15 10:23:45 host sshd[1234]: ...")
        self.assertEqual(ts, "Mar 15 10:23:45")

    def test_time_only(self):
        ts = detect_timestamp("10:23:45 started task")
        self.assertEqual(ts, "10:23:45")

    def test_no_timestamp(self):
        self.assertIsNone(detect_timestamp("just some plain text"))


class TestParseLine(unittest.TestCase):
    """Комплексный парсинг строки."""

    def test_full_iso_error(self):
        pl = parse_line("2025-03-15 10:23:45.123 [ERROR] Something failed")
        self.assertEqual(pl.level, "ERROR")
        self.assertEqual(pl.timestamp, "2025-03-15 10:23:45.123")

    def test_only_level(self):
        pl = parse_line("WARN: retry")
        self.assertEqual(pl.level, "WARN")
        self.assertIsNone(pl.timestamp)

    def test_only_timestamp(self):
        pl = parse_line("2025-01-01 00:00:00 - some event")
        self.assertIsNone(pl.level)
        self.assertEqual(pl.timestamp, "2025-01-01 00:00:00")

    def test_empty(self):
        pl = parse_line("")
        self.assertIsNone(pl.level)
        self.assertIsNone(pl.timestamp)


class TestTimestampToDatetime(unittest.TestCase):
    """Преобразование timestamp в datetime для отчётов."""

    def test_iso_with_ms(self):
        dt = timestamp_to_datetime("2025-03-15T10:23:45.123")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2025)
        self.assertEqual(dt.hour, 10)

    def test_iso_with_timezone_stripped(self):
        dt = timestamp_to_datetime("2025-03-15T10:23:45Z")
        self.assertIsNotNone(dt)

    def test_space_separator(self):
        dt = timestamp_to_datetime("2025-03-15 10:23:45")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.day, 15)

    def test_invalid(self):
        self.assertIsNone(timestamp_to_datetime("not a date"))

    def test_empty(self):
        self.assertIsNone(timestamp_to_datetime(""))


if __name__ == "__main__":
    unittest.main()
