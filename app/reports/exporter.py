"""Экспорт данных в CSV / JSON / HTML / TXT.

Использует потоковую запись (по одной строке), чтобы не раздувать память
при экспорте больших объёмов.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


Row = Tuple[int, Optional[str], Optional[str], str]
# (line_number, level, timestamp, text)


def export_csv(rows: Iterable[Row], path: str | Path, delimiter: str = ",") -> int:
    """Экспортировать в CSV. Возвращает количество записанных строк."""
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["line_number", "level", "timestamp", "text"])
        for row in rows:
            w.writerow(row)
            count += 1
    return count


def export_json(rows: Iterable[Row], path: str | Path) -> int:
    """Экспортировать в JSON-массив."""
    data: List[dict] = []
    for line_number, level, timestamp, text in rows:
        data.append({
            "line_number": line_number,
            "level": level,
            "timestamp": timestamp,
            "text": text,
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return len(data)


def export_html(rows: Iterable[Row], path: str | Path, title: str = "Log Export") -> int:
    """Экспортировать в HTML-таблицу с подсветкой уровней."""
    count = 0
    colors = {
        "ERROR": "#FFE0E0",
        "WARN":  "#FFF5CC",
        "INFO":  "#E0F5E0",
        "DEBUG": "#E8E8F0",
        "TRACE": "#F0F0F0",
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title>"
            "<style>"
            "body{font-family:sans-serif;font-size:13px;margin:20px}"
            "table{border-collapse:collapse;width:100%}"
            "th,td{border:1px solid #ccc;padding:4px 8px;vertical-align:top}"
            "th{background:#f0f0f0;position:sticky;top:0}"
            "td.num{text-align:right;color:#888;font-family:monospace}"
            "td.level{font-weight:bold;text-align:center}"
            "td.text{font-family:monospace;white-space:pre-wrap}"
            "</style></head><body>"
            f"<h1>{html.escape(title)}</h1><table>"
            "<thead><tr><th>№</th><th>Уровень</th><th>Время</th><th>Сообщение</th></tr></thead>"
            "<tbody>"
        )
        for line_number, level, timestamp, text in rows:
            bg = colors.get(level or "", "transparent")
            f.write(
                f"<tr style='background:{bg}'>"
                f"<td class='num'>{line_number}</td>"
                f"<td class='level'>{html.escape(level or '')}</td>"
                f"<td>{html.escape(timestamp or '')}</td>"
                f"<td class='text'>{html.escape(text)}</td></tr>"
            )
            count += 1
        f.write("</tbody></table></body></html>")
    return count


def export_txt(rows: Iterable[Row], path: str | Path) -> int:
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for line_number, level, timestamp, text in rows:
            f.write(f"[{line_number}] [{level or '---'}] [{timestamp or '---'}] {text}\n")
            count += 1
    return count


EXPORTERS = {
    "CSV":  export_csv,
    "JSON": export_json,
    "HTML": export_html,
    "TXT":  export_txt,
}
