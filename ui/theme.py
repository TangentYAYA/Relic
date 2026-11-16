from PySide6.QtWidgets import QApplication


PALETTE = {
    "background": "#0b1118",
    "surface": "#121c26",
    "surface_alt": "#172431",
    "sidebar": "#101a25",
    "border": "#263746",
    "text": "#e6eef5",
    "muted": "#8fa3b5",
    "accent": "#36c5e8",
    "accent_dark": "#123c4a",
    "success": "#45d483",
    "warning": "#e7b85c",
    "danger": "#ef6b73",
}


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(
        f"""
        * {{ font-family: "Segoe UI"; font-size: 13px; }}
        QMainWindow, QWidget {{ background: {PALETTE["background"]}; color: {PALETTE["text"]}; }}
        QFrame#sidebar {{ background: {PALETTE["sidebar"]}; border-right: 1px solid {PALETTE["border"]}; }}
        QLabel#brand {{ color: {PALETTE["accent"]}; font-size: 22px; font-weight: 700; }}
        QLabel#eyebrow {{ color: {PALETTE["accent"]}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
        QLabel#pageTitle {{ color: {PALETTE["text"]}; font-size: 26px; font-weight: 700; }}
        QLabel#muted {{ color: {PALETTE["muted"]}; }}
        QToolButton#navButton {{
            background: transparent; border: 0; border-radius: 6px;
            color: {PALETTE["muted"]}; text-align: left; padding: 11px 14px;
        }}
        QToolButton#navButton:hover {{ background: {PALETTE["surface_alt"]}; color: {PALETTE["text"]}; }}
        QToolButton#navButton:checked {{ background: {PALETTE["accent_dark"]}; color: {PALETTE["accent"]}; }}
        QFrame#card {{ background: {PALETTE["surface"]}; border: 1px solid {PALETTE["border"]}; border-radius: 8px; }}
        QPushButton {{
            background: {PALETTE["surface_alt"]}; border: 1px solid {PALETTE["border"]};
            border-radius: 5px; color: {PALETTE["text"]}; padding: 8px 14px;
        }}
        QPushButton:hover {{ border-color: {PALETTE["accent"]}; }}
        QPushButton#primary {{ background: {PALETTE["accent"]}; color: #071017; border: 0; font-weight: 700; }}
        QLineEdit, QComboBox {{
            background: {PALETTE["surface"]}; border: 1px solid {PALETTE["border"]};
            border-radius: 5px; padding: 8px; color: {PALETTE["text"]};
        }}
        QTableView, QTreeView, QListWidget {{
            background: {PALETTE["surface"]}; alternate-background-color: #15212c;
            border: 1px solid {PALETTE["border"]}; border-radius: 6px;
            gridline-color: {PALETTE["border"]}; selection-background-color: {PALETTE["accent_dark"]};
        }}
        QHeaderView::section {{ background: {PALETTE["surface_alt"]}; color: {PALETTE["muted"]}; border: 0; padding: 8px; }}
        QProgressBar {{ background: {PALETTE["surface_alt"]}; border: 0; border-radius: 4px; text-align: center; }}
        QProgressBar::chunk {{ background: {PALETTE["accent"]}; border-radius: 4px; }}
        QStatusBar {{ background: {PALETTE["sidebar"]}; color: {PALETTE["muted"]}; }}
        """
    )

