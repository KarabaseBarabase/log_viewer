"""Инициализация SQLite и схема БД.

Используется sqlite3 из стандартной библиотеки (без ORM) — так проще,
прозрачнее и быстрее для sparse-индекса миллионов строк.

Схема соответствует ER-диаграмме из пояснительной записки:
    files ←— line_indexes
    saved_filters (независимая)
    highlight_patterns (независимая)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import DB_PATH


SCHEMA = """
-- Открытые файлы и их метаданные
CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT UNIQUE NOT NULL,
    total_lines     INTEGER DEFAULT 0,
    file_size       INTEGER NOT NULL,
    first_timestamp TEXT,
    last_timestamp  TEXT,
    last_opened     DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Sparse-индекс позиций строк (каждая N-я + все ERROR/WARN)
CREATE TABLE IF NOT EXISTS line_indexes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id      INTEGER NOT NULL,
    line_number  INTEGER NOT NULL,
    byte_offset  INTEGER NOT NULL,
    line_length  INTEGER NOT NULL,
    level        TEXT,
    timestamp    TEXT,
    FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_line_file ON line_indexes(file_id, line_number);
CREATE INDEX IF NOT EXISTS idx_line_level ON line_indexes(file_id, level);
CREATE INDEX IF NOT EXISTS idx_line_timestamp ON line_indexes(file_id, timestamp);

-- Сохранённые пользовательские фильтры
CREATE TABLE IF NOT EXISTS saved_filters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    pattern    TEXT,
    is_regex   INTEGER DEFAULT 0,
    levels     TEXT,
    created    DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Пользовательские регулярки для подсветки
CREATE TABLE IF NOT EXISTS highlight_patterns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern    TEXT NOT NULL,
    color      TEXT NOT NULL,
    is_regex   INTEGER DEFAULT 1,
    enabled    INTEGER DEFAULT 1
);

-- Недавно открытые файлы
CREATE TABLE IF NOT EXISTS recent_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT UNIQUE NOT NULL,
    opened_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Открывает соединение с БД и включает foreign keys."""
    path = str(db_path) if db_path else str(DB_PATH)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Ускорение записи (курсовая — не критичные данные, кэш можно потерять)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: Path | str | None = None) -> None:
    """Создаёт таблицы, если их ещё нет."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
