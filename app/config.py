"""Конфигурация приложения.

Содержит константы: пути, размеры буферов, регулярные выражения для парсинга,
цветовые схемы для уровней логирования.
"""
from __future__ import annotations

import os
from pathlib import Path


APP_DIR = Path.home() / ".log_viewer"
APP_DIR.mkdir(exist_ok=True)

DB_PATH = APP_DIR / "cache.db"
LOG_PATH = APP_DIR / "app.log"
SETTINGS_PATH = APP_DIR / "settings.json"


# Сколько строк подгружать за один fetchMore()
FETCH_BATCH_SIZE = 200

# Максимум строк в памяти модели (LRU-кэш). При превышении старые выгружаются.
MAX_LINES_IN_MEMORY = 10_000

# Размер блока при индексации файла (байт)
INDEX_CHUNK_SIZE = 1024 * 1024  # 1 МБ

# Частота sparse-индекса: каждая N-я строка попадает в line_indexes
# (плюс всегда все ERROR/WARN)
SPARSE_INDEX_STEP = 100


LEVELS = ("ERROR", "WARN", "INFO", "DEBUG", "TRACE")

# Регулярки для определения уровня в строке (по порядку приоритета)
LEVEL_PATTERNS = [
    ("ERROR", r"\b(ERROR|ERR|FATAL|SEVERE|CRITICAL)\b"),
    ("WARN",  r"\b(WARN|WARNING)\b"),
    ("INFO",  r"\b(INFO|NOTICE)\b"),
    ("DEBUG", r"\b(DEBUG|FINE)\b"),
    ("TRACE", r"\b(TRACE|VERBOSE|FINEST)\b"),
]


# Регулярки для извлечения timestamp (пробуются по очереди)
TIMESTAMP_PATTERNS = [
    # ISO 8601: 2025-03-15T10:23:45.123Z, 2025-03-15 10:23:45
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
    # Syslog: Mar 15 10:23:45
    r"[A-Z][a-z]{2} [ 0-9]\d \d{2}:\d{2}:\d{2}",
    # Простое: 10:23:45 или 10:23:45.123
    r"\d{2}:\d{2}:\d{2}(?:\.\d+)?",
]


LIGHT_THEME = {
    "ERROR":   "#FFE0E0",
    "WARN":    "#FFF5CC",
    "INFO":    "#E0F5E0",
    "DEBUG":   "#E8E8F0",
    "TRACE":   "#F0F0F0",
    "bg":      "#FFFFFF",
    "fg":      "#222222",
    "accent":  "#0066CC",
}

DARK_THEME = {
    "ERROR":   "#4A1E1E",
    "WARN":    "#4A3E1E",
    "INFO":    "#1E4A26",
    "DEBUG":   "#2A2A3A",
    "TRACE":   "#2A2A2A",
    "bg":      "#1E1E1E",
    "fg":      "#DDDDDD",
    "accent":  "#4A9EFF",
}


LOG_FILE_FILTER = "Log files (*.log *.txt *.out);;All files (*.*)"


APP_NAME = "Log Viewer"
APP_VERSION = "1.0.0"
