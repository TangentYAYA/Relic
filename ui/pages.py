from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSplitter, QTableView, QTabWidget, QTextBrowser, QPlainTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from services.case_service import CaseService
from services.evidence_service import EvidenceService
from services.file_service import FileService
from services.analysis_service import AnalysisService
from services.task_engine import AnalysisTaskEngine
from services.timeline_service import TimelineService
from services.integrity_service import IntegrityService
from services.report_service import ReportService
from domain.models import FileEntry
from .models import TableModel
from .theme import PALETTE
from .widgets import Card, EmptyState, MetricCard, StatusBadge, configure_table, progress_card


class Page(QWidget):
    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(30, 26, 30, 26)
        self.root.setSpacing(18)
        heading = QVBoxLayout()
        eyebrow = QLabel("RELIC / DIGITAL FORENSICS WORKSTATION")
        eyebrow.setObjectName("eyebrow")
        heading.addWidget(eyebrow)
        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")
        heading.addWidget(title_label)
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("muted")
        heading.addWidget(subtitle_label)
        self.root.addLayout(heading)


class _HashSignals(QObject):
    finished = Signal(str)
    failed = Signal(str)


class _HashTask(QRunnable):
    def __init__(self, evidence_service, evidence):
        super().__init__()
        self.service = evidence_service
        self.evidence = evidence
        self.signals = _HashSignals()

    def run(self):
        try:
            digest = self.service.calculate_baseline(self.evidence)
            self.signals.finished.emit(digest)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class _FileSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _ListingTask(QRunnable):
    def __init__(self, service, evidence, offset):
        super().__init__()
        self.service, self.evidence, self.offset = service, evidence, offset
        self.signals = _FileSignals()

    def run(self):
        try:
            listing, _ = self.service.write_listing(self.evidence, self.offset)
            entries = self.service.list_files(self.evidence, self.offset)
            self.signals.finished.emit((listing, entries))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class _ExportTask(QRunnable):
    def __init__(self, service, evidence, offset, entry):
        super().__init__()
        self.service, self.evidence = service, evidence
        self.offset, self.entry = offset, entry
        self.signals = _FileSignals()

    def run(self):
        try:
            record = self.service.export_file(
                self.evidence, self.offset, self.entry.inode, self.entry.name
            )
            self.signals.finished.emit(record)
        except Exception as exc:
            self.signals.failed.emit(str(exc))


class _SearchTask(QRunnable):
    def __init__(self, service, paths, keyword):
        super().__init__()
        self.service, self.paths, self.keyword = service, paths, keyword
        self.signals = _FileSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.service.search_text(self.paths, self.keyword))
        except Exception as exc:
            self.signals.failed.emit(str(exc))


def table_card(headers: list[str], rows: list[list[str]], title: str = "") -> Card:
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 16)
    if title:
        label = QLabel(title)
        label.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(label)
    table = QTableView()
    table.setModel(TableModel(headers, rows, table))
    configure_table(table)
    layout.addWidget(table)
    return card


class DashboardPage(Page):
    def __init__(self, navigate, parent=None):
        super().__init__("Dashboard", "案件概览、完整性状态和分析任务的统一入口。", parent)
        metrics = QHBoxLayout()
        for label, value, caption, tone in [
            ("Active case", "—", "尚未打开案件", PALETTE["accent"]),
            ("Evidence", "0", "等待加载证据", PALETTE["muted"]),
            ("Integrity", "PENDING", "尚未执行复核", PALETTE["warning"]),
            ("Tasks", "0", "没有运行中的任务", PALETTE["muted"]),
        ]:
            metrics.addWidget(MetricCard(label, value, caption, tone))
        self.root.addLayout(metrics)
        row = QHBoxLayout()
        welcome = Card()
        welcome_layout = QVBoxLayout(welcome)
        welcome_layout.addWidget(QLabel("开始一次可追溯的取证工作流"))
        welcome_layout.addWidget(QLabel("这是 UI 演示原型。案件、证据和分析服务尚未接入，所有状态均明确标记为待实现。"))
        welcome_layout.addWidget(QLabel("建议顺序：创建案件 → 注册只读证据 → 执行完整性基线 → 浏览文件系统。"), 0)
        button = QPushButton("前往案件管理")
        button.setObjectName("primary")
        button.clicked.connect(lambda: navigate("案件管理"))
        welcome_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
        row.addWidget(welcome, 2)
        row.addWidget(progress_card("系统准备度", 18, "UI prototype"), 1)
        self.root.addLayout(row)
        self.root.addWidget(EmptyState("没有最近活动", "连接真实服务后，这里将显示审计事件和最近分析任务。"))
        self.root.addStretch()


class CasesPage(Page):
    def __init__(self, case_service: CaseService, parent=None):
        super().__init__("案件管理", "案件生命周期与案件数据隔离。", parent)
        self.case_service = case_service
        toolbar = QHBoxLayout()
        create = QPushButton("新建案件")
        create.setObjectName("primary")
        create.clicked.connect(self._create_case)
        toolbar.addWidget(create)
        open_button = QPushButton("打开选中案件")
        open_button.clicked.connect(self._open_case)
        toolbar.addWidget(open_button)
        edit_button = QPushButton("编辑选中案件")
        edit_button.clicked.connect(self._edit_case)
        toolbar.addWidget(edit_button)
        close_button = QPushButton("关闭当前案件")
        close_button.clicked.connect(self._close_case)
        toolbar.addWidget(close_button)
        toolbar.addStretch()
        self.status = QLabel("案件服务已连接")
        self.status.setObjectName("muted")
        toolbar.addWidget(self.status)
        self.root.addLayout(toolbar)
        self.table = QTableView()
        self.table.setModel(TableModel([], [], self.table))
        configure_table(self.table)
        self.root.addWidget(self.table)
        self._refresh()
        self.root.addStretch()

    def _refresh(self):
        rows = [[case.case_number, case.name, case.examiner, case.status, case.created_at] for case in self.case_service.list_cases()]
        self.table.setModel(TableModel(["案件编号", "案件名称", "取证人员", "状态", "创建时间"], rows, self.table))
        configure_table(self.table)

    def _create_case(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("新建案件")
        form = QFormLayout(dialog)
        fields = [QLineEdit() for _ in range(5)]
        for label, field in zip(["案件编号", "案件名称", "取证人员", "取证对象", "案件描述"], fields):
            form.addRow(label, field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted and all(field.text().strip() for field in fields[:3]):
            self.case_service.create_case(*(field.text().strip() for field in fields))
            self._refresh()
            self.status.setText("案件已创建并打开")

    def _open_case(self):
        row = self.table.currentIndex().row()
        cases = self.case_service.list_cases()
        if 0 <= row < len(cases):
            self.case_service.open_case(cases[row].case_id)
            self._refresh()
            self.status.setText(f"已打开：{cases[row].name}")

    def _close_case(self):
        self.case_service.close_case()
        self._refresh()
        self.status.setText("当前案件已关闭")

    def _edit_case(self):
        row = self.table.currentIndex().row()
        cases = self.case_service.list_cases()
        if not 0 <= row < len(cases):
            self.status.setText("请先选择案件")
            return
        case = cases[row]
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑案件元数据")
        form = QFormLayout(dialog)
        fields = [QLineEdit(value) for value in [case.case_number, case.name, case.examiner, case.subject, case.description]]
        for label, field in zip(["案件编号", "案件名称", "取证人员", "取证对象", "案件描述"], fields):
            form.addRow(label, field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted and all(field.text().strip() for field in fields[:3]):
            case.case_number, case.name, case.examiner, case.subject, case.description = (
                field.text().strip() for field in fields
            )
            self.case_service.update_case(case)
            self._refresh()
            self.status.setText("案件元数据已保存")


class EvidencePage(Page):
    def __init__(self, evidence_service: EvidenceService, parent=None):
        super().__init__("证据管理", "只读镜像注册、SHA-256 基线和分区识别状态。", parent)
        self.evidence_service = evidence_service
        self.evidence = []
        toolbar = QHBoxLayout()
        add = QPushButton("注册 RAW 镜像")
        add.setObjectName("primary")
        add.clicked.connect(self._load_image)
        toolbar.addWidget(add)
        hash_button = QPushButton("固定 SHA-256 基线")
        hash_button.clicked.connect(self._hash_selected)
        toolbar.addWidget(hash_button)
        fs_button = QPushButton("识别选定文件系统")
        fs_button.clicked.connect(self._inspect_filesystem)
        toolbar.addWidget(fs_button)
        toolbar.addStretch()
        self.status = QLabel("原始镜像只读打开；派生数据写入案件目录")
        self.status.setObjectName("muted")
        toolbar.addWidget(self.status)
        self.root.addLayout(toolbar)
        self.table = QTableView()
        self.table.setModel(TableModel([], [], self.table))
        configure_table(self.table)
        self.root.addWidget(self.table)
        self.partition_label = QLabel("选择证据后查看分区")
        self.partition_label.setObjectName("muted")
        self.root.addWidget(self.partition_label)

    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择 RAW/dd 镜像", "", "Disk images (*.raw *.dd *.img);;All files (*)")
        if not path:
            return
        try:
            evidence = self.evidence_service.load_raw(Path(path))
            self.evidence.append(evidence)
            self._refresh()
            self.status.setText(f"已加载 {evidence.name}，原始文件未被写入")
        except Exception as exc:
            QMessageBox.critical(self, "证据加载失败", str(exc))

    def _refresh(self):
        rows = [[item.name, str(item.size_bytes), item.sha256 or "未计算", item.hash_status, str(len(item.partitions))] for item in self.evidence]
        self.table.setModel(TableModel(["证据名称", "大小", "SHA-256", "哈希状态", "分区"], rows, self.table))
        configure_table(self.table)
        if self.evidence:
            self.partition_label.setText("; ".join(f"{p.index}: {p.description} @ {p.start_sector}" for p in self.evidence[-1].partitions))

    def _selected(self):
        row = self.table.currentIndex().row()
        return self.evidence[row] if 0 <= row < len(self.evidence) else None

    def _hash_selected(self):
        evidence = self._selected()
        if evidence is None:
            self.status.setText("请先选择证据")
            return
        try:
            task = _HashTask(self.evidence_service, evidence)
            task.signals.finished.connect(self._hash_finished)
            task.signals.failed.connect(self._hash_failed)
            self.status.setText("正在后台计算 SHA-256…")
            QThreadPool.globalInstance().start(task)
        except Exception as exc:
            self._hash_failed(str(exc))

    def _hash_finished(self, digest: str):
        self._refresh()
        self.status.setText(f"SHA-256 基线已保存：{digest}")

    def _hash_failed(self, message: str):
        QMessageBox.critical(self, "哈希失败", message)

    def _inspect_filesystem(self):
        evidence = self._selected()
        if evidence is None or not evidence.partitions:
            self.status.setText("请先选择含分区的证据")
            return
        try:
            partition = next((item for item in evidence.partitions if item.allocated), evidence.partitions[0])
            info = self.evidence_service.inspect_filesystem(evidence, partition.index)
            self.status.setText(f"文件系统：{info.filesystem_type}")
        except Exception as exc:
            QMessageBox.critical(self, "文件系统识别失败", str(exc))


class FileSystemPage(Page):
    def __init__(self, evidence_service: EvidenceService, file_service: FileService, parent=None):
        super().__init__("文件系统分析", "目录树、文件清单与 inode 详情的三栏工作区。", parent)
        self.evidence_service = evidence_service
        self.file_service = file_service
        self.entries: list[FileEntry] = []
        self.current_evidence = None
        self.current_offset = 0
        controls = QHBoxLayout()
        self.evidence_combo = QComboBox()
        self.evidence_combo.setPlaceholderText("选择已加载证据")
        controls.addWidget(self.evidence_combo, 2)
        load = QPushButton("加载根目录")
        load.clicked.connect(self._load_root)
        controls.addWidget(load)
        self.name_filter = QLineEdit()
        self.name_filter.setPlaceholderText("文件名筛选")
        self.name_filter.textChanged.connect(self._refresh_table)
        controls.addWidget(self.name_filter)
        self.extension_filter = QLineEdit()
        self.extension_filter.setPlaceholderText("扩展名，如 .txt")
        self.extension_filter.textChanged.connect(self._refresh_table)
        controls.addWidget(self.extension_filter)
        self.root.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["目录"])
        splitter.addWidget(self.tree)
        self.table = QTableView()
        self.table.clicked.connect(self._show_details)
        self.table.doubleClicked.connect(self._open_directory)
        configure_table(self.table)
        splitter.addWidget(self.table)
        self.detail = QLabel("选择文件后显示 istat 元数据")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("muted")
        splitter.addWidget(self.detail)
        splitter.setSizes([220, 560, 280])
        self.root.addWidget(splitter, 1)
        actions = QHBoxLayout()
        stat = QPushButton("读取 istat")
        stat.clicked.connect(self._show_details)
        actions.addWidget(stat)
        export = QPushButton("导出选中文件")
        export.setObjectName("primary")
        export.clicked.connect(self._export_selected)
        actions.addWidget(export)
        actions.addStretch()
        self.status = QLabel("文件系统服务已连接")
        self.status.setObjectName("muted")
        actions.addWidget(self.status)
        self.root.addLayout(actions)
        self._refresh_evidence()

    def _refresh_evidence(self):
        self.evidence_combo.clear()
        for evidence in self.evidence_service.loaded_evidence:
            self.evidence_combo.addItem(evidence.name, evidence)

    def _load_root(self):
        self._refresh_evidence()
        evidence = self.evidence_combo.currentData()
        if evidence is None:
            self.status.setText("请先在证据管理中加载 RAW 镜像")
            return
        self.current_evidence = evidence
        self.current_offset = next((p.start_sector for p in evidence.partitions if p.allocated), 0)
        task = _ListingTask(self.file_service, evidence, self.current_offset)
        task.signals.finished.connect(self._listing_finished)
        task.signals.failed.connect(lambda message: QMessageBox.critical(self, "文件清单失败", message))
        self.status.setText("正在后台读取 fls 文件清单…")
        QThreadPool.globalInstance().start(task)

    def _listing_finished(self, result):
        listing, self.entries = result
        self._refresh_table()
        self.status.setText(f"已加载根目录：{len(self.entries)} 项；JSONL：{listing.name}")

    def _refresh_table(self):
        name = self.name_filter.text().casefold()
        extension = self.extension_filter.text().casefold()
        rows = [
            [entry.name, entry.path, str(entry.size_bytes), str(entry.inode), entry.entry_type]
            for entry in self.entries
            if (not name or name in entry.name.casefold())
            and (not extension or entry.name.casefold().endswith(extension))
        ]
        self.table.setModel(TableModel(["名称", "路径", "大小", "inode", "类型"], rows, self.table))
        configure_table(self.table)

    def _selected_entry(self):
        row = self.table.currentIndex().row()
        name = self.name_filter.text().casefold()
        extension = self.extension_filter.text().casefold()
        filtered = [
            entry for entry in self.entries
            if (not name or name in entry.name.casefold())
            and (not extension or entry.name.casefold().endswith(extension))
        ]
        return filtered[row] if 0 <= row < len(filtered) else None

    def _show_details(self, *_):
        entry = self._selected_entry()
        if entry is None or self.current_evidence is None:
            return
        try:
            raw = self.file_service.stat(self.current_evidence, self.current_offset, entry.inode)
            self.detail.setText(
                f"{entry.path}\n inode: {entry.inode}\n size: {entry.size_bytes} bytes\n"
                f"MAC: {entry.modified_at or 'unknown'} / {entry.accessed_at or 'unknown'}\n\n{raw}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "istat 失败", str(exc))

    def _open_directory(self, *_):
        entry = self._selected_entry()
        if entry is None or entry.entry_type != "directory" or self.current_evidence is None:
            return
        try:
            self.entries = self.file_service.list_files(
                self.current_evidence, self.current_offset, inode=entry.inode
            )
            self._refresh_table()
            self.status.setText(f"已打开目录：{entry.path}")
        except Exception as exc:
            QMessageBox.critical(self, "目录浏览失败", str(exc))

    def _export_selected(self):
        entry = self._selected_entry()
        if entry is None or self.current_evidence is None:
            self.status.setText("请先选择文件")
            return
        task = _ExportTask(self.file_service, self.current_evidence, self.current_offset, entry)
        task.signals.finished.connect(lambda record: self.status.setText(f"已导出并计算 SHA-256：{record.sha256}"))
        task.signals.failed.connect(lambda message: QMessageBox.critical(self, "文件导出失败", message))
        self.status.setText("正在后台导出文件…")
        QThreadPool.globalInstance().start(task)


class ContentPage(Page):
    def __init__(self, analysis_service: AnalysisService, parent=None):
        super().__init__("内容分析中心", "签名识别、关键词、EXIF 与文件标记任务。", parent)
        self.analysis_service = analysis_service
        actions = QHBoxLayout()
        type_button = QPushButton("文件类型识别")
        type_button.clicked.connect(self._identify)
        actions.addWidget(type_button)
        exif_button = QPushButton("EXIF 提取")
        exif_button.clicked.connect(self._exif)
        actions.addWidget(exif_button)
        search_button = QPushButton("关键词搜索")
        search_button.clicked.connect(self._search)
        actions.addWidget(search_button)
        annotation_button = QPushButton("添加标记")
        annotation_button.clicked.connect(self._annotate)
        actions.addWidget(annotation_button)
        actions.addStretch()
        self.status = QLabel("演示模式：分析任务尚未提交")
        self.status.setObjectName("muted")
        actions.addWidget(self.status)
        self.root.addLayout(actions)
        self.root.addWidget(EmptyState("选择文件开始分析", "分析结果来自独立 AnalysisService；未知格式会明确标记为 unknown。"))

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择案件派生文件", "", "All files (*)")
        return Path(path) if path else None

    def _identify(self):
        path = self._choose_file()
        if path:
            result = self.analysis_service.identify_type(path)
            self.status.setText(f"{result.data.get('detected_type')} · 扩展名异常={result.data.get('extension_mismatch')}")

    def _exif(self):
        path = self._choose_file()
        if path:
            result = self.analysis_service.extract_metadata(path)
            self.status.setText(
                f"EXIF: {result.data.get('device_model') or '无设备字段'} · "
                f"{result.data.get('width', '')}x{result.data.get('height', '')}"
            )

    def _search(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择纯文本文件", "", "All files (*)")
        if not paths:
            return
        keyword, ok = QInputDialog.getText(self, "关键词搜索", "关键词：")
        if ok and keyword:
            task = _SearchTask(self.analysis_service, [Path(path) for path in paths], keyword)
            task.signals.finished.connect(
                lambda result: self.status.setText(f"命中 {result.data['match_count']} 个位置；结果已持久化")
            )
            task.signals.failed.connect(lambda message: QMessageBox.critical(self, "搜索失败", message))
            self.status.setText("正在后台搜索纯文本文件…")
            QThreadPool.globalInstance().start(task)

    def _annotate(self):
        entry_id, ok = QInputDialog.getText(self, "文件标记", "文件 ID 或路径：")
        if not ok or not entry_id:
            return
        label, ok = QInputDialog.getItem(
            self, "标记类型", "选择：", ["important", "suspicious", "to_analyze"], 0, False
        )
        if ok:
            self.analysis_service.set_annotation(entry_id, label, "")
            self.status.setText("标记已保存并写入审计日志")


class TimelinePage(Page):
    def __init__(self, timeline_service: TimelineService, parent=None):
        super().__init__("时间线分析", "统一展示文件 MAC 时间和来源命令。", parent)
        self.service = timeline_service
        controls = QHBoxLayout()
        self.type_filter = QLineEdit()
        self.type_filter.setPlaceholderText("事件类型筛选")
        controls.addWidget(self.type_filter)
        refresh = QPushButton("刷新时间线")
        refresh.clicked.connect(self._refresh)
        controls.addWidget(refresh)
        controls.addWidget(QLabel("显示时区：UTC"))
        self.root.addLayout(controls)
        self.table = QTableView()
        self.table.clicked.connect(self._show_event)
        configure_table(self.table)
        self.root.addWidget(self.table, 1)
        self.detail = QLabel("选择事件查看来源和对象")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        self.root.addWidget(self.detail)
        self._refresh()

    def _refresh(self):
        types = {self.type_filter.text().strip()} if self.type_filter.text().strip() else None
        self.events = self.service.events(event_types=types)
        self.table.setModel(TableModel(
            ["时间（UTC）", "类型", "来源", "摘要", "文件"],
            [[item.timestamp, item.event_type, item.source_kind, item.summary, item.file_path or ""]
             for item in self.events],
            self.table,
        ))
        configure_table(self.table)

    def _show_event(self, index):
        if index.isValid() and index.row() < len(self.events):
            event = self.events[index.row()]
            self.detail.setText(
                f"{event.timestamp} UTC\n{event.summary}\n"
                f"source={event.source_kind}, object={event.object_id or '—'}"
            )


class TasksPage(Page):
    def __init__(self, task_engine: AnalysisTaskEngine, parent=None):
        super().__init__("分析任务中心", "统一查看任务状态、进度、结果和错误。", parent)
        self.engine = task_engine
        controls = QHBoxLayout()
        refresh = QPushButton("刷新任务")
        refresh.clicked.connect(self._refresh)
        controls.addWidget(refresh)
        cancel = QPushButton("取消选中任务")
        cancel.clicked.connect(self._cancel)
        controls.addWidget(cancel)
        controls.addStretch()
        controls.addWidget(QLabel("状态：pending / running / completed / failed / cancelled"))
        self.root.addLayout(controls)
        self.table = QTableView()
        configure_table(self.table)
        self.root.addWidget(self.table, 1)
        self.status = QLabel("任务引擎已连接")
        self.status.setObjectName("muted")
        self.root.addWidget(self.status)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(500)
        self._refresh()

    def _refresh(self):
        self.tasks = self.engine.history()
        self.table.setModel(TableModel(
            ["任务", "状态", "进度", "开始时间", "结束时间", "错误"],
            [[item.task_name, item.status, f"{item.progress}%", item.start_time or "",
              item.end_time or "", item.error_message or ""] for item in self.tasks],
            self.table,
        ))
        configure_table(self.table)

    def _cancel(self):
        row = self.table.currentIndex().row()
        if 0 <= row < len(self.tasks):
            self.engine.cancel(self.tasks[row].task_id)
            self.status.setText("已请求取消任务")


class IntegrityPage(Page):
    def __init__(self, integrity_service: IntegrityService, parent=None):
        super().__init__("完整性与审计中心", "哈希复核、审计哈希链和自动化质量检查。", parent)
        self.service = integrity_service
        metrics = QHBoxLayout()
        metrics.addWidget(MetricCard("Hash baseline", "PENDING", "等待证据注册", PALETTE["warning"]))
        metrics.addWidget(MetricCard("Audit chain", "PENDING", "尚未创建审计记录", PALETTE["warning"]))
        metrics.addWidget(MetricCard("Quality checks", "0 / 0", "没有可检查项目", PALETTE["muted"]))
        self.root.addLayout(metrics)
        controls = QHBoxLayout()
        refresh = QPushButton("刷新检查")
        refresh.clicked.connect(self._refresh)
        controls.addWidget(refresh)
        checkpoint = QPushButton("创建检查点")
        checkpoint.clicked.connect(self._checkpoint)
        controls.addWidget(checkpoint)
        verify = QPushButton("验证审计链")
        verify.clicked.connect(self._refresh)
        controls.addWidget(verify)
        end_hash = QPushButton("结束复核")
        end_hash.clicked.connect(self._verify_evidence)
        controls.addWidget(end_hash)
        controls.addStretch()
        controls.addWidget(QLabel("哈希链不能阻止拥有文件系统权限者重写整个日志"))
        self.root.addLayout(controls)
        self.summary_table = QTableView()
        configure_table(self.summary_table)
        self.root.addWidget(self.summary_table)
        self.table = QTableView()
        configure_table(self.table)
        self.root.addWidget(self.table, 1)
        self.status = QLabel("检查点位于案件根数据目录外层；信任边界取决于该目录权限")
        self.status.setObjectName("muted")
        self.root.addWidget(self.status)
        self._refresh()

    def _refresh(self):
        summary = self.service.summary()
        self.summary_table.setModel(TableModel(
            ["完整性项目", "值", "状态"],
            [[item["item"], item["value"], item["status"]] for item in summary],
            self.summary_table,
        ))
        configure_table(self.summary_table)
        checks = self.service.quality_checks()
        self.table.setModel(TableModel(
            ["检查项", "状态", "详情"],
            [[item["name"], item["status"], item["details"]] for item in checks],
            self.table,
        ))
        configure_table(self.table)
        audit = self.service.audit_status()
        self.status.setText(
            f"审计链：{'通过' if audit['chain']['valid'] else '异常'}；"
            f"检查点：{audit['checkpoint']['status']}；显示时区：UTC"
        )

    def _verify_evidence(self):
        try:
            verified = self.service.verify_evidence()
            self.status.setText(f"结束复核完成：{verified} 个证据通过")
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, "结束复核失败", str(exc))

    def _checkpoint(self):
        try:
            checkpoint = self.service.create_checkpoint()
            self.status.setText(
                f"检查点已保存：sequence={checkpoint['last_sequence']}，"
                "信任边界取决于案件数据目录权限"
            )
            self._refresh()
        except Exception as exc:
            QMessageBox.critical(self, "检查点失败", str(exc))


class ReportsPage(Page):
    def __init__(self, report_service: ReportService, parent=None):
        super().__init__("报告中心", "仅生成基于真实持久化数据的 Markdown 取证报告。", parent)
        self.service = report_service
        row = QHBoxLayout()
        button = QPushButton("生成 Markdown 报告")
        button.setObjectName("primary")
        button.clicked.connect(self._generate)
        row.addWidget(button)
        self.status = QLabel("报告服务已连接：只生成 Markdown")
        self.status.setObjectName("muted")
        row.addWidget(self.status)
        row.addStretch()
        self.root.addLayout(row)
        self.tabs = QTabWidget()
        self.preview = QTextBrowser()
        self.source = QPlainTextEdit()
        self.source.setReadOnly(True)
        self.tabs.addTab(self.preview, "Markdown 预览")
        self.tabs.addTab(self.source, "Markdown 源码")
        self.root.addWidget(self.tabs, 1)

    def _generate(self):
        try:
            path = self.service.generate()
            content = self.service.preview(path)
            self.preview.setMarkdown(content)
            self.source.setPlainText(content)
            self.status.setText(f"已生成：{path}")
        except Exception as exc:
            QMessageBox.critical(self, "报告生成失败", str(exc))


class SettingsPage(Page):
    def __init__(self, parent=None):
        super().__init__("系统设置", "配置显示偏好与外部工具诊断。", parent)
        card = Card()
        form = QFormLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.addRow("TSK CLI 目录", QLineEdit("未配置（演示）"))
        form.addRow("案件工作目录", QLineEdit("未配置（演示）"))
        form.addRow("主题", QLabel("Dark Forensics"))
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.clicked.connect(lambda: self.status.setText("设置服务尚未接入，未写入配置文件。"))
        form.addRow("", save)
        self.root.addWidget(card)
        self.status = QLabel("演示模式：设置不会写入磁盘")
        self.status.setObjectName("muted")
        self.root.addWidget(self.status)
        self.root.addStretch()
