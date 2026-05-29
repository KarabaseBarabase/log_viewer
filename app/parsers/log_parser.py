"""Парсинг строки лога.

Определяет уровень (ERROR/WARN/INFO/DEBUG/TRACE) и извлекает timestamp.
Парсеры не делают предположений о конкретном формате — работают через
регулярные выражения и пробуют несколько шаблонов по очереди.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.config import LEVEL_PATTERNS, TIMESTAMP_PATTERNS


# Предкомпилированные регулярки (важно для производительности: строк могут быть миллионы)
_LEVEL_RE = [(lvl, re.compile(pat, re.IGNORECASE)) for lvl, pat in LEVEL_PATTERNS]
_TS_RE = [re.compile(pat) for pat in TIMESTAMP_PATTERNS]


@dataclass(frozen=True)
class ParsedLine:
    """Результат парсинга одной строки лога."""
    level: Optional[str]      # ERROR/WARN/... или None, если не определён
    timestamp: Optional[str]  # строка с датой/временем (без парсинга в datetime)
    # Текст строки в объекте не храним — он загружается лениво по byte_offset


def detect_level(line: str) -> Optional[str]:
    """Определить уровень логирования по содержимому строки.

    Возвращает первый найденный уровень из LEVEL_PATTERNS или None.
    Поиск выполняется только в первых 200 символах — защита от очень
    длинных строк со стек-трейсами.
    """
    head = line[:200]
    for level, pattern in _LEVEL_RE:
        if pattern.search(head):
            return level
    return None


def detect_timestamp(line: str) -> Optional[str]:
    """Извлечь timestamp из строки.

    Пробует последовательно паттерны из TIMESTAMP_PATTERNS и возвращает
    первое совпадение как строку (без преобразования в datetime — это
    делается лениво только для отчётов, чтобы не тормозить индексацию).
    """
    head = line[:100]
    for pattern in _TS_RE:
        m = pattern.search(head)
        if m:
            return m.group(0)
    return None


def parse_line(line: str) -> ParsedLine:
    """Полный парсинг строки: уровень + timestamp."""
    return ParsedLine(
        level=detect_level(line),
        timestamp=detect_timestamp(line),
    )


def timestamp_to_datetime(ts: str) -> Optional[datetime]:
    """Преобразовать строку timestamp в datetime (для отчётов).

    Пробует несколько форматов. Если не удалось — возвращает None.
    """
    if not ts:
        return None

    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%H:%M:%S.%f",
        "%H:%M:%S",
    ]

    # Убираем 'Z' и таймзоны в конце (упрощение)
    cleaned = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", ts).strip()

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None
