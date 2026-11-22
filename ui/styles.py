# -*- coding: utf-8 -*-
"""PCL2（Plain Craft Launcher 2）风格主题。

还原 PCL2 的标志性视觉：亮蓝顶栏 + 居中导航胶囊 + 白色账号侧栏 +
浅蓝渐变主内容区 + 白色圆角卡片。默认「龙猫蓝」浅色主题。

通过命中功能页面使用的 objectName 实现「外壳焕新、功能页面自动换肤」，
后端与页面逻辑零改动。
"""

_LIGHT = {
    # 顶栏蓝色渐变
    'top1': '#3E97DE', 'top2': '#2676BE',
    # 主区浅蓝渐变
    'bg1': '#EAF3FC', 'bg2': '#D2E4F7',
    'sidebar': '#FFFFFF',
    'card': '#FFFFFF', 'card2': '#F3F7FC',
    'text': '#2A3441', 'sub': '#8B98A9',
    'accent': '#2A79C2', 'accent_hover': '#3589D3', 'accent_press': '#2069AC',
    'border': '#E2EAF4', 'input': '#F0F5FB',
    'navactive': '#FFFFFF',
    'shadow': 'rgba(28,64,110,0.10)',
}

_DARK = {
    'top1': '#20578C', 'top2': '#153F68',
    'bg1': '#1C2835', 'bg2': '#131D28',
    'sidebar': '#1A2531',
    'card': '#1F2C3A', 'card2': '#263546',
    'text': '#E6EEF6', 'sub': '#8C9BAE',
    'accent': '#4EA3E4', 'accent_hover': '#5FB2EE', 'accent_press': '#3C8ECD',
    'border': '#31404F', 'input': '#17222E',
    'navactive': '#FFFFFF',
    'shadow': 'rgba(0,0,0,0.35)',
}


def _palette(theme):
    return _LIGHT if theme == 'light' else _DARK


def get_bg(theme):
    return _palette(theme)['bg1']


def get_window_colors(theme):
    """返回主窗口背景渐变的 (上, 下) 两个颜色。"""
    c = _palette(theme)
    return c['bg1'], c['bg2']


def get_stylesheet(theme='light'):
    c = _palette(theme)
    T = {
        'TOP1': c['top1'], 'TOP2': c['top2'],
        'BG1': c['bg1'], 'BG2': c['bg2'],
        'SIDEBAR': c['sidebar'], 'CARD': c['card'], 'CARD2': c['card2'],
        'TEXT': c['text'], 'SUB': c['sub'],
        'ACCENT': c['accent'], 'ACH': c['accent_hover'], 'ACP': c['accent_press'],
        'BORDER': c['border'], 'INPUT': c['input'],
        'NAVACT': c['navactive'],
    }

    QSS = r"""
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: %(TEXT)s;
    background: transparent;
}
QDialog, QDialog#Page {
    background: %(BG1)s;
}

/* ---------- 顶部蓝色标题/导航栏 ---------- */
QWidget#TitleBar {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 %(TOP1)s, stop:1 %(TOP2)s);
}
QLabel#Logo {
    color: #ffffff;
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#LogoSub {
    color: rgba(255,255,255,0.72);
    font-size: 10px;
    letter-spacing: 1px;
}

/* 顶栏窗口按钮 */
QPushButton#WindowButton, QPushButton#close_btn {
    background: transparent;
    border: none;
    border-radius: 5px;
    color: #ffffff;
    font-size: 15px;
    min-width: 38px;
    max-width: 38px;
    min-height: 30px;
    padding: 0;
}
QPushButton#WindowButton:hover, QPushButton#close_btn:hover { background: rgba(255,255,255,0.18); }
QPushButton#close_btn:hover { background: #e5484d; color: #ffffff; }

/* 顶栏导航胶囊 */
QPushButton#NavButton {
    background: transparent;
    border: none;
    border-radius: 15px;
    color: rgba(255,255,255,0.92);
    font-size: 13px;
    font-weight: 600;
    padding: 7px 17px;
}
QPushButton#NavButton:hover { background: rgba(255,255,255,0.16); }
QPushButton#NavButton:checked {
    background: %(NAVACT)s;
    color: %(ACCENT)s;
    font-weight: 800;
}

/* ---------- 左侧白色账号栏 ---------- */
QWidget#SideBar { background: %(SIDEBAR)s; }
QLabel#AccountTag {
    background: %(ACCENT)s;
    color: #ffffff;
    border-radius: 11px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 700;
}
QLabel#AccountTagInactive {
    background: transparent;
    color: %(SUB)s;
    border: 1px solid %(BORDER)s;
    border-radius: 11px;
    padding: 4px 14px;
    font-size: 12px;
}
QLabel#Avatar {
    font-size: 52px;
    color: %(ACCENT)s;
}
QLabel#AccountLabel {
    color: %(TEXT)s;
    font-size: 13px;
    font-weight: 700;
    padding: 2px 0;
}

/* 左下「启动游戏」大按钮 */
QPushButton#LaunchButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 %(ACH)s, stop:1 %(ACCENT)s);
    color: #ffffff;
    border: none;
    border-radius: 9px;
    padding: 12px 8px;
    font-size: 15px;
    font-weight: 800;
    min-height: 46px;
}
QPushButton#LaunchButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 %(ACCENT)s, stop:1 %(ACP)s);
}
QPushButton#LaunchButton:pressed { background: %(ACP)s; }

/* ---------- 主内容区（透明，露出渐变） ---------- */
QStackedWidget#MainArea, QWidget#Page, QScrollArea#Scroll {
    background: transparent;
}
QScrollArea#Scroll QWidget { background: transparent; }
QScrollArea#Scroll { border: none; }

QLabel#PageTitle {
    font-size: 23px;
    font-weight: 800;
    color: %(TEXT)s;
}
QLabel#PageHint, QLabel#Hint { color: %(SUB)s; font-size: 12px; }
QLabel#CardTitle { font-size: 14px; font-weight: 700; color: %(TEXT)s; }
QLabel#CardSub { color: %(SUB)s; font-size: 12px; }
QLabel#SettingLabel { color: %(TEXT)s; font-size: 13px; }
QLabel#TitleText { font-size: 13px; font-weight: 600; color: %(TEXT)s; }
QLabel#TitleIcon { font-size: 16px; color: %(ACCENT)s; }
QLabel#CodeLabel { color: %(ACCENT)s; font-weight: 700; }
QLabel#UrlLabel { color: %(ACCENT)s; }

/* ---------- 卡片 ---------- */
QFrame#Card, QFrame#StagePanel {
    background: %(CARD)s;
    border: 1px solid %(BORDER)s;
    border-radius: 10px;
}
QFrame#SettingRow {
    background: transparent;
    border: none;
}

/* ---------- 按钮 ---------- */
QPushButton {
    background: %(CARD2)s;
    color: %(TEXT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    padding: 7px 14px;
}
QPushButton:hover { background: %(INPUT)s; border-color: %(ACCENT)s; }
QPushButton:pressed { background: %(BORDER)s; }
QPushButton:disabled { color: %(SUB)s; }

QPushButton#PrimaryButton, QPushButton#PlayButton, QPushButton#InstallButton {
    background: %(ACCENT)s;
    color: #ffffff;
    border: none;
    font-weight: 700;
    border-radius: 7px;
}
QPushButton#PrimaryButton:hover, QPushButton#PlayButton:hover, QPushButton#InstallButton:hover {
    background: %(ACH)s;
}
QPushButton#PrimaryButton:pressed, QPushButton#PlayButton:pressed, QPushButton#InstallButton:pressed {
    background: %(ACP)s;
}

QPushButton#GhostButton {
    background: transparent;
    border: 1px solid %(BORDER)s;
    color: %(TEXT)s;
}
QPushButton#GhostButton:hover { border-color: %(ACCENT)s; color: %(ACCENT)s; }

QPushButton#ThemeButton {
    background: transparent;
    border: 1px solid %(BORDER)s;
    border-radius: 6px;
    padding: 5px 9px;
    color: %(SUB)s;
    font-size: 12px;
}
QPushButton#ThemeButton:hover { color: %(ACCENT)s; border-color: %(ACCENT)s; }

/* ---------- 输入控件 ---------- */
QLineEdit, QLineEdit#LineEdit, QSpinBox#Spin, QSpinBox {
    background: %(INPUT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    padding: 7px 10px;
    color: %(TEXT)s;
}
QLineEdit:focus, QSpinBox:focus { border: 1px solid %(ACCENT)s; }

QComboBox, QComboBox#ComboBox {
    background: %(INPUT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    padding: 6px 10px;
    color: %(TEXT)s;
}
QComboBox:hover { border-color: %(ACCENT)s; }
QComboBox QAbstractItemView {
    background: %(CARD)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    color: %(TEXT)s;
    selection-background-color: %(ACCENT)s;
    selection-color: #ffffff;
}

QListWidget, QListWidget#AccountList {
    background: %(INPUT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 8px;
    padding: 3px;
    outline: 0;
}
QListWidget::item {
    border-radius: 5px;
    padding: 5px 8px;
    color: %(TEXT)s;
}
QListWidget::item:hover { background: %(CARD2)s; }
QListWidget::item:selected { background: %(ACCENT)s; color: #ffffff; }

QTextEdit, QPlainTextEdit, QTextEdit#ConsoleText {
    background: %(CARD)s;
    border: 1px solid %(BORDER)s;
    border-radius: 8px;
    padding: 8px;
    color: %(TEXT)s;
    font-family: "Cascadia Code", Consolas, monospace;
    font-size: 12px;
}

/* ---------- 进度条 ---------- */
QProgressBar, QProgressBar#ProgressBar, QProgressBar#StageBar {
    background: %(INPUT)s;
    border: 1px solid %(BORDER)s;
    border-radius: 7px;
    height: 15px;
    text-align: center;
    color: %(TEXT)s;
    font-size: 11px;
}
QProgressBar::chunk, QProgressBar#ProgressBar::chunk, QProgressBar#StageBar::chunk {
    background: %(ACCENT)s;
    border-radius: 6px;
}
QLabel#StageTitle { color: %(TEXT)s; font-weight: 700; }
QLabel#StageTime { color: %(SUB)s; font-size: 11px; }

/* ---------- 其它 ---------- */
QCheckBox { spacing: 6px; color: %(TEXT)s; }
QCheckBox::indicator { width: 16px; height: 16px; }
QCheckBox::indicator:unchecked {
    border: 1px solid %(BORDER)s;
    border-radius: 4px;
    background: %(INPUT)s;
}
QCheckBox::indicator:checked {
    border: 1px solid %(ACCENT)s;
    border-radius: 4px;
    background: %(ACCENT)s;
}

QGroupBox {
    border: 1px solid %(BORDER)s;
    border-radius: 9px;
    margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title { color: %(SUB)s; padding: 0 6px; }

QTabWidget::pane { border: 1px solid %(BORDER)s; border-radius: 9px; top: -1px; }
QTabBar::tab {
    background: %(CARD2)s;
    color: %(SUB)s;
    border: 1px solid %(BORDER)s;
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 7px 16px;
}
QTabBar::tab:selected { color: %(ACCENT)s; background: %(CARD)s; }
QTabBar::tab:hover { color: %(TEXT)s; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical {
    background: %(BORDER)s;
    border-radius: 5px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: %(SUB)s; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
    for k, v in T.items():
        QSS = QSS.replace('%(' + k + ')s', v)
    return QSS
