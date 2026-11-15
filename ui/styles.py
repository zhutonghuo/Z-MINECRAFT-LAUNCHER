# -*- coding: utf-8 -*-
"""PCL 风格的界面主题（深色 / 浅色）。

通过命中旧页面层使用的 objectName（PageTitle / PrimaryButton / GhostButton /
Card / NavButton / LineEdit ...），实现「外壳焕新、功能页面自动换肤」，
后端与页面逻辑零改动。
"""

_LIGHT = {
    'bg': '#eef1f5', 'panel': '#ffffff', 'card': '#ffffff', 'card2': '#f3f6f9',
    'text': '#1b232b', 'sub': '#5d6b79', 'accent': '#119e8b', 'accent2': '#2f7fff',
    'accent_hover': '#13b39d', 'accent_press': '#0f8a7a',
    'border': '#dde3ea', 'input_bg': '#f5f7fa', 'nav_bg': '#f7f9fb',
    'nav_active': '#e3eef0', 'shadow': 'rgba(20,40,60,0.10)',
}

_DARK = {
    'bg': '#0e141a', 'panel': '#161f29', 'card': '#1a2531', 'card2': '#212e3c',
    'text': '#e8eef4', 'sub': '#8a98a6', 'accent': '#21d4b4', 'accent2': '#3a8dff',
    'accent_hover': '#2fe0c1', 'accent_press': '#1bbfa3',
    'border': '#29353f', 'input_bg': '#111a22', 'nav_bg': '#121a23',
    'nav_active': '#1e2a36', 'shadow': 'rgba(0,0,0,0.35)',
}


def _palette(theme):
    return _LIGHT if theme == 'light' else _DARK


def get_bg(theme):
    return _palette(theme)['bg']


def get_stylesheet(theme='dark'):
    c = _palette(theme)
    T = {
        'BG': c['bg'], 'PANEL': c['panel'], 'CARD': c['card'], 'CARD2': c['card2'],
        'TEXT': c['text'], 'SUB': c['sub'], 'ACCENT': c['accent'], 'ACCENT2': c['accent2'],
        'ACH': c['accent_hover'], 'ACP': c['accent_press'], 'BORDER': c['border'],
        'INPUT': c['input_bg'], 'NAV': c['nav_bg'], 'NAVACT': c['nav_active'],
        'SHADOW': c['shadow'],
    }

    QSS = """
QWidget {
    background: %(BG)s;
    color: %(TEXT)s;
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
}
QDialog {
    background: %(BG)s;
}
QLabel { background: transparent; color: %(TEXT)s; }
QLabel#PageTitle {
    font-size: 22px; font-weight: 700; color: %(TEXT)s;
}
QLabel#PageHint, QLabel#Hint { color: %(SUB)s; font-size: 12px; }
QLabel#Brand { font-size: 15px; font-weight: 700; color: %(ACCENT)s; }
QLabel#TitleText { font-size: 13px; font-weight: 600; color: %(TEXT)s; }
QLabel#TitleIcon { font-size: 16px; color: %(ACCENT)s; }
QLabel#AccountLabel { color: %(SUB)s; font-size: 12px; padding: 4px 2px; }
QLabel#CardTitle { font-size: 14px; font-weight: 700; color: %(TEXT)s; }
QLabel#CardSub { color: %(SUB)s; font-size: 12px; }

QPushButton {
    background: %(CARD2)s; color: %(TEXT)s;
    border: 1px solid %(BORDER)s; border-radius: 8px;
    padding: 7px 14px;
}
QPushButton:hover { background: %(NAVACT)s; border-color: %(ACCENT)s; }
QPushButton:pressed { background: %(CARD)s; }
QPushButton:disabled { color: %(SUB)s; background: %(CARD)s; }

QPushButton#PrimaryButton {
    background: %(ACCENT)s; color: #ffffff; border: none; font-weight: 700;
}
QPushButton#PrimaryButton:hover { background: %(ACH)s; }
QPushButton#PrimaryButton:pressed { background: %(ACP)s; }

QPushButton#GhostButton {
    background: transparent; border: 1px solid %(BORDER)s; color: %(TEXT)s;
}
QPushButton#GhostButton:hover { border-color: %(ACCENT)s; color: %(ACCENT)s; }

QPushButton#ThemeButton {
    background: transparent; border: 1px solid %(BORDER)s;
    border-radius: 7px; padding: 5px 10px; color: %(SUB)s; font-size: 12px;
}
QPushButton#ThemeButton:hover { color: %(ACCENT)s; border-color: %(ACCENT)s; }

QPushButton#WindowButton {
    background: transparent; border: none; border-radius: 6px;
    color: %(SUB)s; font-size: 13px; padding: 0; min-width: 36px;
}
QPushButton#WindowButton:hover { background: %(NAVACT)s; color: %(TEXT)s; }
QPushButton#close_btn:hover { background: #e5484d; color: #ffffff; }

QPushButton#NavButton {
    background: transparent; border: none; border-radius: 9px;
    color: %(SUB)s; text-align: left; padding: 10px 14px; font-size: 13px;
}
QPushButton#NavButton:hover { background: %(NAVACT)s; color: %(TEXT)s; }
QPushButton#NavButton:checked {
    background: %(NAVACT)s; color: %(ACCENT)s; font-weight: 700;
}

QFrame#Card {
    background: %(CARD)s; border: 1px solid %(BORDER)s; border-radius: 12px;
}

QLineEdit#LineEdit, QLineEdit {
    background: %(INPUT)s; border: 1px solid %(BORDER)s; border-radius: 8px;
    padding: 7px 10px; color: %(TEXT)s;
}
QLineEdit:focus { border: 1px solid %(ACCENT)s; }

QProgressBar#ProgressBar {
    background: %(INPUT)s; border: 1px solid %(BORDER)s; border-radius: 7px;
    height: 14px; text-align: center; color: %(TEXT)s; font-size: 11px;
}
QProgressBar#ProgressBar::chunk {
    background: %(ACCENT)s; border-radius: 6px;
}

QListWidget#AccountList, QListWidget {
    background: %(INPUT)s; border: 1px solid %(BORDER)s; border-radius: 10px;
    padding: 4px; outline: 0;
}
QListWidget::item {
    border-radius: 7px; padding: 6px 8px; color: %(TEXT)s;
}
QListWidget::item:hover { background: %(NAVACT)s; }
QListWidget::item:selected { background: %(NAVACT)s; color: %(ACCENT)s; }

QTextEdit {
    background: %(INPUT)s; border: 1px solid %(BORDER)s; border-radius: 8px;
    padding: 8px; color: %(TEXT)s; font-family: "Cascadia Code", Consolas, monospace;
    font-size: 12px;
}

QComboBox {
    background: %(INPUT)s; border: 1px solid %(BORDER)s; border-radius: 8px;
    padding: 6px 10px; color: %(TEXT)s;
}
QComboBox:hover { border-color: %(ACCENT)s; }
QComboBox QAbstractItemView {
    background: %(CARD)s; border: 1px solid %(BORDER)s; border-radius: 8px;
    color: %(TEXT)s; selection-background-color: %(NAVACT)s;
}

QScrollBar:vertical {
    background: transparent; width: 10px; margin: 2px;
}
QScrollBar::handle:vertical {
    background: %(BORDER)s; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: %(SUB)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QTabWidget::pane { border: 1px solid %(BORDER)s; border-radius: 10px; top: -1px; }
QTabBar::tab {
    background: %(CARD2)s; color: %(SUB)s; border: 1px solid %(BORDER)s;
    border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px;
    padding: 7px 16px;
}
QTabBar::tab:selected { color: %(ACCENT)s; background: %(CARD)s; }
QTabBar::tab:hover { color: %(TEXT)s; }

QCheckBox { spacing: 6px; color: %(TEXT)s; }
QCheckBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked {
    border: 1px solid %(BORDER)s; border-radius: 4px; background: %(INPUT)s;
}
QCheckBox::indicator:checked {
    border: 1px solid %(ACCENT)s; border-radius: 4px; background: %(ACCENT)s;
}

QGroupBox {
    border: 1px solid %(BORDER)s; border-radius: 10px; margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title { color: %(SUB)s; padding: 0 6px; }
"""
    for k, v in T.items():
        QSS = QSS.replace('%' + k + '%', v)
    return QSS
