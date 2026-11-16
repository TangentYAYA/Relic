from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QProgressBar, QTableView,
    QVBoxLayout, QWidget,
)

from .theme import PALETTE


class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")


class EmptyState(Card):
    actionRequested = Signal()

    def __init__(self, title: str, message: str, action: str | None = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
        layout.addWidget(title_label)
        detail = QLabel(message)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)
        if action:
            button = QPushButton(action)
            button.setObjectName("primary")
            button.clicked.connect(self.actionRequested)
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)


class MetricCard(Card):
    def __init__(self, label: str, value: str, caption: str, tone: str = PALETTE["accent"], parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        label_widget = QLabel(label.upper())
        label_widget.setObjectName("eyebrow")
        layout.addWidget(label_widget)
        value_widget = QLabel(value)
        value_widget.setStyleSheet(f"font-size: 27px; font-weight: 700; color: {tone};")
        layout.addWidget(value_widget)
        caption_widget = QLabel(caption)
        caption_widget.setObjectName("muted")
        layout.addWidget(caption_widget)


class StatusBadge(QLabel):
    def __init__(self, text: str, color: str = PALETTE["muted"], parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color: {color}; background: {color}22; border-radius: 4px; padding: 3px 7px;"
        )


def configure_table(table: QTableView) -> None:
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
    table.horizontalHeader().setStretchLastSection(True)
    table.verticalHeader().setVisible(False)


def progress_card(title: str, value: int, detail: str) -> Card:
    card = Card()
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 16)
    row = QHBoxLayout()
    row.addWidget(QLabel(title))
    row.addStretch()
    row.addWidget(QLabel(detail))
    layout.addLayout(row)
    progress = QProgressBar()
    progress.setValue(value)
    progress.setTextVisible(False)
    layout.addWidget(progress)
    return card

