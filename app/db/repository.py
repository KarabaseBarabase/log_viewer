"""Репозиторий — весь SQL в одном месте.

Используется паттерн Repository: код приложения не работает с SQL напрямую,
а вызывает методы этого класса. Это упрощает тестирование и даёт возможность
в будущем заменить SQLite на другую БД без переписывания views/models.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, List, Optional, Sequence, Tuple

from app.db.database import get_connection


IndexRow = Tuple[int, int, int, Optional[str], Optional[str]]
# (line_number, byte_offset, line_length, level, timestamp)


class Repository:
    """Фасад для операций с БД."""

    def __init__(self, conn: sqlite3.Connection | None = None):
        self._conn = conn or get_connection()


    def upsert_file(self, path: str, file_size: int) -> int:
        """Создать запись о файле или обновить last_opened, если уже был."""
        cur = self._conn.execute(
            "SELECT id FROM files WHERE path = ?", (path,)
        )
        row = cur.fetchone()
        if row:
            self._conn.execute(
                "UPDATE files SET file_size = ?, last_opened = CURRENT_TIMESTAMP "
                "WHERE id = ?", (file_size, row["id"])
            )
            self._conn.commit()
            # В recent_files тоже обновим
            self._touch_recent(path)
            return int(row["id"])

        cur = self._conn.execute(
            "INSERT INTO files(path, file_size) VALUES(?, ?)",
            (path, file_size),
        )
        self._conn.commit()
        self._touch_recent(path)
        return int(cur.lastrowid)

    def update_file_stats(
        self,
        file_id: int,
        *,
        total_lines: Optional[int] = None,
        first_ts: Optional[str] = None,
        last_ts: Optional[str] = None,
    ) -> None:
        fields, params = [], []
        if total_lines is not None:
            fields.append("total_lines = ?"); params.append(total_lines)
        if first_ts is not None:
            fields.append("first_timestamp = ?"); params.append(first_ts)
        if last_ts is not None:
            fields.append("last_timestamp = ?"); params.append(last_ts)
        if not fields:
            return
        params.append(file_id)
        self._conn.execute(f"UPDATE files SET {', '.join(fields)} WHERE id = ?", params)
        self._conn.commit()

    def get_file(self, file_id: int) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        return cur.fetchone()

    def get_file_by_path(self, path: str) -> Optional[sqlite3.Row]:
        cur = self._conn.execute("SELECT * FROM files WHERE path = ?", (path,))
        return cur.fetchone()

    # line_indexes

    def clear_indexes(self, file_id: int) -> None:
        self._conn.execute("DELETE FROM line_indexes WHERE file_id = ?", (file_id,))
        self._conn.commit()

    def flush_indexes(self, batch: Sequence[IndexRow], file_id: int | None = None) -> None:
        """Батчевая вставка индексов.

        batch: список кортежей (line_number, byte_offset, line_length, level, timestamp).
        file_id передаётся для всех строк батча.
        """
        if not batch:
            return
        # Если file_id задан — подставляем в каждую строку
        if file_id is not None:
            rows = [(file_id, *row) for row in batch]
            self._conn.executemany(
                "INSERT INTO line_indexes(file_id, line_number, byte_offset, "
                "line_length, level, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        else:
            # Если file_id уже в batch (для совместимости)
            self._conn.executemany(
                "INSERT INTO line_indexes(file_id, line_number, byte_offset, "
                "line_length, level, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
        self._conn.commit()

    def get_indexes(
        self,
        file_id: int,
        *,
        levels: Optional[Iterable[str]] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[sqlite3.Row]:
        """Получить индексы строк с опциональной фильтрацией по уровню."""
        sql = "SELECT * FROM line_indexes WHERE file_id = ?"
        params: List = [file_id]
        if levels:
            placeholders = ",".join("?" * len(list(levels)))
            sql += f" AND level IN ({placeholders})"
            params.extend(levels)
        sql += " ORDER BY line_number"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        return self._conn.execute(sql, params).fetchall()

    def count_by_level(self, file_id: int) -> dict[str, int]:
        """Сколько строк каждого уровня (из sparse-индекса — для ошибок точное,
        для INFO/DEBUG приблизительное, что допустимо для статистики)."""
        cur = self._conn.execute(
            "SELECT level, COUNT(*) as cnt FROM line_indexes "
            "WHERE file_id = ? AND level IS NOT NULL GROUP BY level",
            (file_id,),
        )
        return {r["level"]: r["cnt"] for r in cur.fetchall()}

    def errors_per_hour(self, file_id: int) -> List[Tuple[str, int]]:
        """Для отчёта: количество ERROR по часам (ключ — 'YYYY-MM-DD HH')."""
        cur = self._conn.execute(
            "SELECT substr(timestamp, 1, 13) AS hour, COUNT(*) as cnt "
            "FROM line_indexes "
            "WHERE file_id = ? AND level = 'ERROR' AND timestamp IS NOT NULL "
            "GROUP BY hour ORDER BY hour",
            (file_id,),
        )
        return [(r["hour"], r["cnt"]) for r in cur.fetchall()]

    def get_heatmap(self, file_id: int, buckets: int = 200) -> List[int]:
        """Для мини-карты: распределение ошибок по позиции в файле.

        Возвращает массив из `buckets` значений — сколько ERROR/WARN в каждом
        «ведре» (bucket) по номеру строки.
        """
        row = self._conn.execute(
            "SELECT total_lines FROM files WHERE id = ?", (file_id,)
        ).fetchone()
        if not row or not row["total_lines"]:
            return [0] * buckets

        total = row["total_lines"]
        bucket_size = max(1, total // buckets)

        result = [0] * buckets
        cur = self._conn.execute(
            "SELECT line_number FROM line_indexes "
            "WHERE file_id = ? AND level IN ('ERROR', 'WARN')",
            (file_id,),
        )
        for r in cur.fetchall():
            idx = min(buckets - 1, (r["line_number"] - 1) // bucket_size)
            result[idx] += 1
        return result

    def top_messages(self, file_id: int, limit: int = 10) -> List[Tuple[str, int, str]]:
        """Топ-N самых частых сообщений (уникальный текст timestamp+level).

        ВНИМАНИЕ: точный топ требует прочитать все строки (т.к. text в индексе
        не хранится). Для курсовой используем приближение: считаем по
        (level, первые 80 символов от timestamp), что достаточно для
        демонстрации отчёта. В пояснительной записке это оговорено.
        """
        cur = self._conn.execute(
            "SELECT level, COUNT(*) as cnt, MAX(timestamp) as last_ts "
            "FROM line_indexes "
            "WHERE file_id = ? AND level IS NOT NULL "
            "GROUP BY level ORDER BY cnt DESC LIMIT ?",
            (file_id, limit),
        )
        return [(r["level"], r["cnt"], r["last_ts"] or "") for r in cur.fetchall()]

    # saved_filters

    def save_filter(self, name: str, pattern: str, is_regex: bool, levels: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO saved_filters(name, pattern, is_regex, levels) "
            "VALUES (?, ?, ?, ?)",
            (name, pattern, int(is_regex), levels),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_filters(self) -> List[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM saved_filters ORDER BY created DESC"
        ).fetchall()

    def delete_filter(self, filter_id: int) -> None:
        self._conn.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
        self._conn.commit()

    # highlight_patterns

    def list_patterns(self) -> List[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM highlight_patterns WHERE enabled = 1"
        ).fetchall()

    def add_pattern(self, pattern: str, color: str, is_regex: bool = True) -> int:
        cur = self._conn.execute(
            "INSERT INTO highlight_patterns(pattern, color, is_regex) VALUES (?, ?, ?)",
            (pattern, color, int(is_regex)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def delete_pattern(self, pattern_id: int) -> None:
        self._conn.execute("DELETE FROM highlight_patterns WHERE id = ?", (pattern_id,))
        self._conn.commit()

    # recent_files

    def _touch_recent(self, path: str) -> None:
        self._conn.execute(
            "INSERT INTO recent_files(path) VALUES (?) "
            "ON CONFLICT(path) DO UPDATE SET opened_at = CURRENT_TIMESTAMP",
            (path,),
        )
        self._conn.commit()

    def recent(self, limit: int = 10) -> List[str]:
        cur = self._conn.execute(
            "SELECT path FROM recent_files ORDER BY opened_at DESC LIMIT ?",
            (limit,),
        )
        return [r["path"] for r in cur.fetchall()]


    def close(self) -> None:
        self._conn.close()
