"""Design tokens and the global Qt stylesheet (dark theme)."""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

C = {
    "bg": "#0B0D12",
    "bg2": "#10131A",
    "surface": "#151922",
    "surface2": "#1B202B",
    "surface3": "#232938",
    "border": "#262D3B",
    "border2": "#333C4F",
    "text": "#E8ECF4",
    "text2": "#A3ACBF",
    "text3": "#6B7489",
    "accent": "#7C6CFF",
    "accent2": "#9D8FFF",
    "accent_dim": "#2A2550",
    "cyan": "#3DD6D0",
    "success": "#34D399",
    "success_dim": "#0F3B2E",
    "danger": "#F87171",
    "danger_dim": "#3F1D22",
    "warning": "#FBBF24",
    "warning_dim": "#3D3113",
    "info": "#60A5FA",
}

ACTION_COLORS = {
    "CLICK": "#7C6CFF", "DOUBLE_CLICK": "#A78BFA", "RIGHT_CLICK": "#F472B6",
    "DRAG": "#3DD6D0", "SCROLL": "#60A5FA", "INPUT": "#FBBF24", "KEY": "#FB923C", "WAIT": "#94A3B8",
}

STATUS_COLORS = {
    "PASSED": C["success"], "FAILED": C["danger"], "SKIPPED": C["text3"],
    "STOPPED": C["warning"], "RUNNING": C["accent"], "COMPLETED": C["success"],
}

RADIUS = 12


def pick_font_family() -> str:
    families = set(QFontDatabase.families())
    for f in ("Inter", "Segoe UI Variable Text", "Segoe UI", "Cantarell", "Noto Sans", "Ubuntu", "DejaVu Sans"):
        if f in families:
            return f
    return QFont().defaultFamily()


def apply_palette(app):
    from uiv_studio.core.paths import resource_dir
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C["bg"]))
    pal.setColor(QPalette.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.Base, QColor(C["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(C["surface2"]))
    pal.setColor(QPalette.Text, QColor(C["text"]))
    pal.setColor(QPalette.Button, QColor(C["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.Highlight, QColor(C["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    pal.setColor(QPalette.ToolTipBase, QColor(C["surface3"]))
    pal.setColor(QPalette.ToolTipText, QColor(C["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(C["text3"]))
    app.setPalette(pal)
    font = QFont(pick_font_family(), 10)
    font.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET.replace("{CHEVRON}", (resource_dir() / "chevron.svg").as_posix()))


STYLESHEET = f"""
* {{ outline: none; }}
QWidget {{ color: {C['text']}; font-size: 10pt; }}
QMainWindow, #Root {{ background: {C['bg']}; }}
QToolTip {{ background: {C['surface3']}; color: {C['text']}; border: 1px solid {C['border2']};
            border-radius: 6px; padding: 6px 8px; }}

QLabel#H1 {{ font-size: 22pt; font-weight: 700; }}
QLabel#H2 {{ font-size: 15pt; font-weight: 650; }}
QLabel#H3 {{ font-size: 11.5pt; font-weight: 600; }}
QLabel#Muted {{ color: {C['text2']}; }}
QLabel#Faint {{ color: {C['text3']}; font-size: 9pt; }}
QLabel#Eyebrow {{ color: {C['accent2']}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1.5px; }}

QFrame#Card, QFrame#Panel {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: {RADIUS}px; }}
QFrame#Sidebar {{ background: {C['bg2']}; border-right: 1px solid {C['border']}; }}
QFrame#Divider {{ background: {C['border']}; max-height: 1px; min-height: 1px; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {C['bg2']}; border: 1px solid {C['border']}; border-radius: 8px;
    padding: 7px 10px; selection-background-color: {C['accent']};
}}
QLineEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {C['border2']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {C['accent']}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {C['text3']}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url("{{CHEVRON}}"); width: 12px; height: 12px; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: {C['surface2']}; border: 1px solid {C['border2']}; border-radius: 8px;
                               padding: 4px; selection-background-color: {C['accent_dim']}; }}

QPushButton {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 9px;
               padding: 8px 16px; font-weight: 600; }}
QPushButton:hover {{ background: {C['surface3']}; border-color: {C['border2']}; }}
QPushButton:pressed {{ background: {C['border']}; }}
QPushButton:disabled {{ color: {C['text3']}; background: {C['surface']}; }}
QPushButton#Primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['accent']}, stop:1 #5B8CFF);
                       border: none; color: white; }}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['accent2']}, stop:1 #74A0FF); }}
QPushButton#Primary:disabled {{ background: {C['accent_dim']}; color: {C['text3']}; }}
QPushButton#Danger {{ background: {C['danger_dim']}; border: 1px solid #5B2A31; color: {C['danger']}; }}
QPushButton#Danger:hover {{ background: #52242B; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {C['text2']}; }}
QPushButton#Ghost:hover {{ background: {C['surface2']}; color: {C['text']}; }}
QToolButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton:hover {{ background: {C['surface3']}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border2']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {C['text3']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {C['border2']}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background: none; border: none; width: 0; height: 0; }}

QListWidget, QTreeWidget, QTableWidget {{ background: transparent; border: none; }}
QListWidget::item {{ border-radius: 10px; }}
QListWidget::item:selected {{ background: transparent; }}

QSlider::groove:horizontal {{ height: 4px; background: {C['surface3']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C['accent']}, stop:1 {C['cyan']}); border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
                              border: 3px solid {C['accent']}; }}
QSlider::handle:horizontal:hover {{ border-color: {C['accent2']}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {C['border2']}; background: {C['bg2']}; }}
QCheckBox::indicator:checked {{ background: {C['accent']}; border-color: {C['accent']}; }}

QMenu {{ background: {C['surface2']}; border: 1px solid {C['border2']}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {C['accent_dim']}; }}
QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 8px; }}

QTabBar::tab {{ background: transparent; color: {C['text2']}; padding: 8px 14px; border: none; font-weight: 600; }}
QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}
QTabWidget::pane {{ border: none; }}

QDialog {{ background: {C['bg2']}; }}
QMessageBox {{ background: {C['bg2']}; }}
QSplitter::handle {{ background: {C['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
"""
