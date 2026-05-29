"""Точка входа приложения.

Запуск: `python -m app.main`
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from app.config import APP_NAME
from app.views.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("log_viewer")

    win = MainWindow()
    win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
