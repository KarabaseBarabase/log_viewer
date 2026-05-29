"""Форма 1: Главное окно приложения.

Содержит:
    - Меню (Файл, Правка, Вид, Отчёты, Справка)
    - Панель инструментов
    - Центральный QSplitter: слева — дерево навигации, справа — просмотрщик
    - Статусная строка (путь, число строк, активный фильтр)
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
    QVBoxLayout,
)

from app.config import APP_NAME, APP_VERSION, DARK_THEME, LIGHT_THEME, LOG_FILE_FILTER
from app.db.database import init_db
from app.db.repository import Repository
from app.models.filter_state import FilterState
from app.models.log_model import LogTableModel
from app.models.tree_model import NavigationTreeModel
from app.parsers.indexer import IndexerThread
from app.views.log_viewer_widget import LogViewerWidget
from app.views.navigation_tree import NavigationTreeWidget
from app.views.filter_panel import FilterPanel
from app.views.search_dialog import SearchDialog
from app.views.open_dialog import OpenFileDialog
from app.views.frequency_report import FrequencyReportDialog
from app.views.top_messages_report import TopMessagesDialog
from app.views.pattern_manager import PatternManagerDialog
from app.views.export_dialog import ExportDialog
from app.views.statistics_dialog import StatisticsDialog
from app.views.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    """Главное окно Log Viewer."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1400, 900)

        # БД и репозиторий
        init_db()
        self._repo = Repository()

        # Текущий открытый файл
        self._current_file_id: Optional[int] = None
        self._current_file_path: Optional[str] = None
        self._log_model: Optional[LogTableModel] = None
        self._tree_model: Optional[NavigationTreeModel] = None
        self._indexer: Optional[IndexerThread] = None
        self._progress: Optional[QProgressDialog] = None
        self._theme = LIGHT_THEME

        # Загружаем настройки окна (размер/позиция) и пользовательские настройки
        self._settings = QSettings("log_viewer", "main")

        # UI
        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

        # Применяем сохранённые пользовательские настройки (тема, шрифт)
        self._apply_user_settings()

        geom = self._settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)


    def _build_ui(self) -> None:
        # Центральный сплиттер
        self._splitter = QSplitter(Qt.Orientation.Horizontal)

        # Левая панель: дерево навигации
        self._tree_widget = NavigationTreeWidget()
        self._tree_widget.nodeActivated.connect(self._on_tree_navigate)
        self._splitter.addWidget(self._tree_widget)

        # Правая панель: фильтр + просмотрщик
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._filter_panel = FilterPanel(self._repo)
        self._filter_panel.filterChanged.connect(self._on_filter_changed)
        right_layout.addWidget(self._filter_panel)

        self._log_view = LogViewerWidget()
        self._log_view.showInTreeRequested.connect(self._on_show_in_tree)
        right_layout.addWidget(self._log_view, stretch=1)

        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 4)
        self._splitter.setSizes([300, 1100])

        self.setCentralWidget(self._splitter)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # Файл
        m_file = mb.addMenu("&Файл")

        act_open = QAction("&Открыть...", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._action_open_file)
        m_file.addAction(act_open)

        act_open_dlg = QAction("Открыть (расширенный)...", self)
        act_open_dlg.triggered.connect(self._action_open_file_advanced)
        m_file.addAction(act_open_dlg)

        self._menu_recent = m_file.addMenu("Недавние файлы")
        self._refresh_recent_menu()

        m_file.addSeparator()

        act_stats = QAction("&Статистика файла...", self)
        act_stats.triggered.connect(self._action_statistics)
        m_file.addAction(act_stats)

        m_file.addSeparator()
        act_exit = QAction("В&ыход", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.triggered.connect(self.close)
        m_file.addAction(act_exit)

        # Правка
        m_edit = mb.addMenu("&Правка")

        act_find = QAction("&Найти...", self)
        act_find.setShortcut(QKeySequence.StandardKey.Find)
        act_find.triggered.connect(self._action_search)
        m_edit.addAction(act_find)

        act_clear_filter = QAction("&Сбросить фильтр", self)
        act_clear_filter.triggered.connect(self._filter_panel.reset)
        m_edit.addAction(act_clear_filter)

        act_patterns = QAction("Менеджер &паттернов...", self)
        act_patterns.triggered.connect(self._action_patterns)
        m_edit.addAction(act_patterns)

        # Вид
        m_view = mb.addMenu("&Вид")
        act_theme = QAction("Тёмная тема", self, checkable=True)
        act_theme.triggered.connect(self._toggle_theme)
        self._act_theme = act_theme
        m_view.addAction(act_theme)

        # Отчёты
        m_reports = mb.addMenu("&Отчёты")

        act_freq = QAction("&Частота ошибок по времени...", self)
        act_freq.triggered.connect(self._action_frequency_report)
        m_reports.addAction(act_freq)

        act_top = QAction("&Топ сообщений...", self)
        act_top.triggered.connect(self._action_top_report)
        m_reports.addAction(act_top)

        m_reports.addSeparator()
        act_export = QAction("&Экспорт...", self)
        act_export.triggered.connect(self._action_export)
        m_reports.addAction(act_export)

        # Настройки
        m_tools = mb.addMenu("&Инструменты")
        act_settings = QAction("&Настройки...", self)
        act_settings.triggered.connect(self._action_settings)
        m_tools.addAction(act_settings)

        # Справка
        m_help = mb.addMenu("&Справка")
        act_about = QAction("О программе...", self)
        act_about.triggered.connect(self._action_about)
        m_help.addAction(act_about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Главная", self)
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize() * 0.8)
        self.addToolBar(tb)

        act_open = QAction("Открыть", self)
        act_open.triggered.connect(self._action_open_file)
        tb.addAction(act_open)

        act_find = QAction("Поиск", self)
        act_find.triggered.connect(self._action_search)
        tb.addAction(act_find)

        act_clear = QAction("Сбросить фильтр", self)
        act_clear.triggered.connect(self._filter_panel.reset)
        tb.addAction(act_clear)

        tb.addSeparator()

        act_freq = QAction("Отчёт по частоте", self)
        act_freq.triggered.connect(self._action_frequency_report)
        tb.addAction(act_freq)

        act_top = QAction("Топ сообщений", self)
        act_top.triggered.connect(self._action_top_report)
        tb.addAction(act_top)

        act_export = QAction("Экспорт", self)
        act_export.triggered.connect(self._action_export)
        tb.addAction(act_export)

    def _build_statusbar(self) -> None:
        sb = QStatusBar(self)
        self._lbl_file = QLabel("Файл не открыт")
        self._lbl_lines = QLabel("")
        self._lbl_filter = QLabel("фильтр: нет")
        sb.addWidget(self._lbl_file, 2)
        sb.addWidget(self._lbl_lines, 1)
        sb.addWidget(self._lbl_filter, 2)
        self.setStatusBar(sb)


    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(f"""
            QMainWindow, QDialog, QWidget {{
                background: {t['bg']};
                color: {t['fg']};
            }}
            QToolBar, QMenuBar, QMenu, QStatusBar {{
                background: {t['bg']};
                color: {t['fg']};
            }}
            QTableView, QTreeView, QListView {{
                background: {t['bg']};
                color: {t['fg']};
                gridline-color: #888;
                selection-background-color: {t['accent']};
                selection-color: white;
            }}
            QHeaderView::section {{
                background: {t['bg']};
                color: {t['fg']};
                border: 1px solid #666;
                padding: 2px 6px;
            }}
            QLineEdit, QComboBox, QDateTimeEdit {{
                background: {t['bg']};
                color: {t['fg']};
                border: 1px solid #888;
                padding: 2px 4px;
            }}
        """)
        if self._log_model:
            self._log_model.set_theme(t)
        if self._tree_model:
            self._tree_model.set_theme(t)

    def _toggle_theme(self, checked: bool) -> None:
        self._theme = DARK_THEME if checked else LIGHT_THEME
        # Сохраняем в QSettings, чтобы при следующем запуске и в диалоге настроек было то же значение
        self._settings.setValue("theme", "Тёмная" if checked else "Светлая")
        self._apply_theme()


    def _action_open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Открыть лог-файл", "", LOG_FILE_FILTER
        )
        if path:
            self._open_file(path)

    def _action_open_file_advanced(self) -> None:
        """Расширенный диалог открытия — Форма 2."""
        dlg = OpenFileDialog(self._repo, self)
        if dlg.exec():
            path = dlg.selected_path()
            if path:
                self._open_file(path)

    def _refresh_recent_menu(self) -> None:
        self._menu_recent.clear()
        for path in self._repo.recent(10):
            a = QAction(path, self)
            a.triggered.connect(lambda _=False, p=path: self._open_file(p))
            self._menu_recent.addAction(a)

    def _open_file(self, path: str) -> None:
        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", f"Файл не найден:\n{path}")
            return

        # Остановить старую индексацию, если есть
        if self._indexer and self._indexer.isRunning():
            self._indexer.cancel()
            self._indexer.wait(1000)

        # Закрыть старую модель (освободить файловый дескриптор)
        if self._log_model:
            self._log_model.close()
            self._log_model = None

        # Запустить индексацию
        self._current_file_path = path
        self._lbl_file.setText(f"Индексация: {path}")
        self._progress = QProgressDialog("Индексация файла...", "Отмена", 0, 100, self)
        self._progress.setWindowTitle("Пожалуйста, подождите")
        self._progress.setMinimumDuration(0)
        self._progress.setValue(0)

        self._indexer = IndexerThread(path, self._repo)
        self._indexer.progress.connect(self._on_index_progress)
        self._indexer.finished_ok.connect(self._on_index_done)
        self._indexer.error.connect(self._on_index_error)
        self._indexer.cancelled.connect(self._on_index_cancelled)
        self._progress.canceled.connect(self._indexer.cancel)
        self._indexer.start()

    def _on_index_progress(self, percent: int, lines: int) -> None:
        if self._progress:
            self._progress.setValue(percent)
            self._progress.setLabelText(
                f"Индексация файла...\nОбработано строк: {lines:,}".replace(",", " ")
            )

    def _on_index_done(self, file_id: int, total_lines: int) -> None:
        self._current_file_id = file_id
        if self._progress:
            self._progress.close()
            self._progress = None

        # Создаём модели
        self._log_model = LogTableModel(file_id, self._current_file_path, self._repo)
        self._log_view.set_model(self._log_model)

        self._tree_model = NavigationTreeModel(self._repo)
        self._tree_model.set_file(file_id, self._current_file_path or "")
        self._tree_widget.set_model(self._tree_model)

        # Применяем текущую тему
        self._log_model.set_theme(self._theme)
        self._tree_model.set_theme(self._theme)

        # Обновляем статус
        self._lbl_file.setText(self._current_file_path or "")
        self._lbl_lines.setText(f"строк: {total_lines:,}".replace(",", " "))
        self._lbl_filter.setText("фильтр: нет")

        # Передаём heatmap в виджет (мини-карта)
        heatmap = self._repo.get_heatmap(file_id, buckets=200)
        self._log_view.set_heatmap(heatmap)

        # Обновим меню «Недавние»
        self._refresh_recent_menu()

    def _on_index_error(self, msg: str) -> None:
        if self._progress:
            self._progress.close()
            self._progress = None
        QMessageBox.critical(self, "Ошибка индексации", msg)

    def _on_index_cancelled(self) -> None:
        """Индексация прервана пользователем — закрыть диалог, сбросить состояние."""
        if self._progress:
            self._progress.close()
            self._progress = None
        self._current_file_path = None
        self._lbl_file.setText("файл не открыт")
        self._lbl_lines.setText("строк: —")
        # Главное окно остаётся пустым, как до открытия файла

    def _on_filter_changed(self, f: FilterState) -> None:
        if self._log_model:
            self._log_model.apply_filter(f)
            self._lbl_filter.setText(f"фильтр: {f.describe()}")
            self._lbl_lines.setText(
                f"показано: {self._log_model.total_matched():,}".replace(",", " ")
            )

    def _on_tree_navigate(self, line_number: int) -> None:
        """Двойной клик по узлу дерева — переходим к строке."""
        if not self._log_model:
            return
        row = self._log_model.find_row_by_line_number(line_number)
        # Подгружаем вперёд, если нужно
        while self._log_model.canFetchMore() and row >= self._log_model.rowCount():
            self._log_model.fetchMore()
        self._log_view.scroll_to_row(row)

    def _on_show_in_tree(self, line_number: int) -> None:
        """Из контекстного меню таблицы — раскрываем дерево навигации."""
        # Без сложной логики поиска точного узла: просто разворачиваем все
        # узлы уровней, чтобы пользователь увидел контекст.
        if hasattr(self, "_tree_widget"):
            self._tree_widget.expand_all()

    def _action_search(self) -> None:
        if not self._log_model:
            QMessageBox.information(self, "Поиск", "Откройте файл перед поиском.")
            return
        dlg = SearchDialog(self._log_model, self)
        dlg.exec()

    def _action_frequency_report(self) -> None:
        if not self._current_file_id:
            QMessageBox.information(self, "Отчёт", "Сначала откройте файл.")
            return
        dlg = FrequencyReportDialog(self._current_file_id, self._repo, self)
        dlg.exec()

    def _action_top_report(self) -> None:
        if not self._current_file_id:
            QMessageBox.information(self, "Отчёт", "Сначала откройте файл.")
            return
        dlg = TopMessagesDialog(self._current_file_id, self._repo, self)
        dlg.navigateTo.connect(self._on_tree_navigate)
        dlg.exec()

    def _action_patterns(self) -> None:
        dlg = PatternManagerDialog(self._repo, self)
        dlg.exec()
        # Применяем изменения сразу — модель перечитывает паттерны из БД и перерисовывается
        if self._log_model is not None:
            self._log_model.reload_patterns()

    def _action_export(self) -> None:
        if not self._log_model:
            QMessageBox.information(self, "Экспорт", "Сначала откройте файл.")
            return
        dlg = ExportDialog(self._log_model, self._current_file_path or "", self)
        dlg.exec()

    def _action_statistics(self) -> None:
        if not self._current_file_id:
            QMessageBox.information(self, "Статистика", "Сначала откройте файл.")
            return
        dlg = StatisticsDialog(self._current_file_id, self._repo, self)
        dlg.exec()

    def _action_settings(self) -> None:
        dlg = SettingsDialog(self)
        if dlg.exec():
            # Применяем сохранённые в QSettings параметры
            self._apply_user_settings()

    def _apply_user_settings(self) -> None:
        """Читает QSettings и применяет тему/шрифт/размер батча к UI.

        Вызывается при старте и после закрытия SettingsDialog (Save).
        """
        # Тема
        theme_name = self._settings.value("theme", "Светлая")
        is_dark = (str(theme_name) == "Тёмная")
        self._theme = DARK_THEME if is_dark else LIGHT_THEME
        # Синхронизируем галочку в меню Вид → Тёмная тема
        if hasattr(self, "_act_theme"):
            self._act_theme.blockSignals(True)
            self._act_theme.setChecked(is_dark)
            self._act_theme.blockSignals(False)
        self._apply_theme()

        # Шрифт таблицы
        family = str(self._settings.value("font_family", "Consolas, Menlo, monospace"))
        size = int(self._settings.value("font_size", 11))
        self._log_view.set_table_font(family, size)

    def _action_about(self) -> None:
        QMessageBox.about(
            self,
            "О программе",
            f"<h2>{APP_NAME} {APP_VERSION}</h2>"
            "<p>Просмотрщик-анализатор лог-файлов.</p>"
            "<p>Курсовая работа по предмету<br>"
            "«Проектирование и разработка интерфейсов информационных систем».</p>"
            "<p>Технологии: Python 3, PyQt6, pyqtgraph, SQLite.</p>"
        )


    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._settings.setValue("geometry", self.saveGeometry())
        if self._indexer and self._indexer.isRunning():
            self._indexer.cancel()
            self._indexer.wait(2000)
        if self._log_model:
            self._log_model.close()
        self._repo.close()
        super().closeEvent(event)
