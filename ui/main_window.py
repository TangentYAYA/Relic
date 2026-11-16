from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QStackedWidget, QStatusBar,
    QToolButton, QVBoxLayout, QWidget,
)
from pathlib import Path
import os

from infrastructure.tsk_adapter import TSKAdapter
from services.file_service import FileService
from services.analysis_service import AnalysisService
from services.task_engine import AnalysisTaskEngine
from services.timeline_service import TimelineService
from services.integrity_service import IntegrityService
from services.report_service import ReportService
from .pages import (
    CasesPage, ContentPage, DashboardPage, EvidencePage, FileSystemPage,
    IntegrityPage, ReportsPage, SettingsPage, TasksPage, TimelinePage,
)
from services.case_service import CaseService
from services.evidence_service import EvidenceService


class MainWindow(QMainWindow):
    NAVIGATION = [
        ("◈", "Dashboard", DashboardPage),
        ("▣", "案件管理", CasesPage),
        ("◉", "证据管理", EvidencePage),
        ("⌘", "文件系统分析", FileSystemPage),
        ("◇", "内容分析中心", ContentPage),
        ("◷", "时间线分析", TimelinePage),
        ("≡", "分析任务中心", TasksPage),
        ("✓", "完整性与审计中心", IntegrityPage),
        ("▤", "报告中心", ReportsPage),
        ("⚙", "系统设置", SettingsPage),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Relic — Digital Forensics & Evidence Integrity Platform")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QToolButton] = {}
        root = Path(os.environ.get("RELIC_CASE_ROOT", str(Path.cwd() / ".relic_data")))
        tsk_bin = Path(os.environ.get("RELIC_TSK_BIN", r"D:\sleuthkit\sleuthkit\bin"))
        self.case_service = CaseService(root)
        self.evidence_service = EvidenceService(self.case_service, TSKAdapter(tsk_bin))
        self.file_service = FileService(self.case_service, TSKAdapter(tsk_bin))
        self.analysis_service = AnalysisService(self.case_service)
        self.task_engine = AnalysisTaskEngine(self.case_service)
        self.timeline_service = TimelineService(self.case_service)
        self.integrity_service = IntegrityService(self.case_service)
        self.report_service = ReportService(
            self.case_service, self.integrity_service, self.timeline_service
        )
        self._register_tasks()
        self._build_ui()

    def _register_tasks(self):
        def file_type(params, progress, cancel):
            progress(20)
            result = self.analysis_service.identify_type(Path(params["path"]))
            progress(100)
            return {"result_id": result.result_id, "data": result.data}

        def keyword_search(params, progress, cancel):
            progress(10)
            if cancel.is_set():
                return {}
            result = self.analysis_service.search_text(
                [Path(item) for item in params["paths"]],
                params["keyword"],
                params.get("case_sensitive", False),
            )
            progress(100)
            return {"result_id": result.result_id, "data": result.data}

        self.task_engine.register("file_type", file_type)
        self.task_engine.register("keyword_search", keyword_search)

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        for _, name, page_type in self.NAVIGATION:
            if page_type is DashboardPage:
                page = page_type(self.navigate)
            elif page_type is CasesPage:
                page = page_type(self.case_service)
            elif page_type is EvidencePage:
                page = page_type(self.evidence_service)
            elif page_type is FileSystemPage:
                page = page_type(self.evidence_service, self.file_service)
            elif page_type is ContentPage:
                page = page_type(self.analysis_service)
            elif page_type is TasksPage:
                page = page_type(self.task_engine)
            elif page_type is TimelinePage:
                page = page_type(self.timeline_service)
            elif page_type is IntegrityPage:
                page = page_type(self.integrity_service)
            elif page_type is ReportsPage:
                page = page_type(self.report_service)
            else:
                page = page_type()
            self.pages[name] = page
            self.stack.addWidget(page)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("核心服务已连接 · 未加载案件 · 分析任务与时间线可用")
        self.navigate("Dashboard")

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(245)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 20)
        layout.setSpacing(5)
        brand = QLabel("RELIC")
        brand.setObjectName("brand")
        layout.addWidget(brand)
        tagline = QLabel("Evidence integrity workstation")
        tagline.setObjectName("muted")
        layout.addWidget(tagline)
        layout.addSpacing(22)
        for icon, name, _ in self.NAVIGATION:
            button = QToolButton()
            button.setObjectName("navButton")
            button.setText(f"{icon}   {name}")
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.clicked.connect(lambda checked=False, target=name: self.navigate(target))
            self.nav_buttons[name] = button
            layout.addWidget(button)
        layout.addStretch()
        footer = QLabel("CORE SERVICES CONNECTED\nTSK / ANALYSIS / TIMELINE")
        footer.setObjectName("muted")
        layout.addWidget(footer)
        return sidebar

    def navigate(self, name: str):
        page = self.pages.get(name)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.nav_buttons[name].setChecked(True)
        self.statusBar().showMessage(f"{name} · 核心服务已连接 · 当前案件数据决定可用结果")
