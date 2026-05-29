"""Состояние фильтра — неизменяемый объект.

Используется как value object: при любом изменении создаётся новая копия
через dataclasses.replace(), что упрощает отладку и тесты.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional


@dataclass(frozen=True)
class FilterState:
    """Параметры фильтрации строк лога."""

    # Текст/регулярка для поиска
    text_pattern: str = ""
    is_regex: bool = False
    case_sensitive: bool = False

    # Множество уровней, которые нужно показывать. Пустое = все уровни.
    levels: FrozenSet[str] = field(default_factory=frozenset)

    # Диапазон времени (строки "YYYY-MM-DD HH:MM:SS"). None = без ограничения.
    time_from: Optional[str] = None
    time_to: Optional[str] = None

    def is_empty(self) -> bool:
        """Фильтр пустой — показываем всё."""
        return (
            not self.text_pattern
            and not self.levels
            and not self.time_from
            and not self.time_to
        )

    def describe(self) -> str:
        """Человекочитаемое описание фильтра (для статусной строки)."""
        parts = []
        if self.text_pattern:
            kind = "regex" if self.is_regex else "текст"
            parts.append(f"{kind}: «{self.text_pattern}»")
        if self.levels:
            parts.append("уровни: " + ",".join(sorted(self.levels)))
        if self.time_from or self.time_to:
            parts.append(f"время: {self.time_from or '...'} — {self.time_to or '...'}")
        return "; ".join(parts) if parts else "нет фильтра"
