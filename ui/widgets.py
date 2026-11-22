# -*- coding: utf-8 -*-
"""PCL2 风格基础控件。

- fmt_size(n)                 体积格式化
- ProgressPanel(QFrame)       下载进度面板（保留 objectName 供换肤）
- TitleBar(QWidget)           PCL2 亮蓝顶栏：左侧 Logo + 居中导航胶囊 + 右侧窗口按钮
- NavButton(QPushButton)      顶栏导航胶囊，点击切页
- LaunchButton(QPushButton)   左下「启动游戏」大按钮
- Card / PrimaryButton / GhostButton  便捷控件
"""
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                             QFrame, QProgressBar, QButtonGroup)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QBrush, QLinearGradient


def fmt_size(n):
    if not n or n <= 0:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    v = float(n)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024.0
        i += 1
    return ('%d B' % int(n)) if i == 0 else ('%.2f %s' % (v, units[i]))


class ProgressPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('Card')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(9)
        self.stage = QLabel('准备下载...')
        self.stage.setObjectName('CardTitle')
        self.bar = QProgressBar()
        self.bar.setObjectName('ProgressBar')
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(True)
        self.detail = QLabel('')
        self.detail.setObjectName('CardSub')
        self.file = QLabel('')
        self.file.setObjectName('PageHint')
        self.file.setWordWrap(True)
        lay.addWidget(self.stage)
        lay.addWidget(self.bar)
        lay.addWidget(self.detail)
        lay.addWidget(self.file)
        self.setVisible(False)

    def show_stage(self, text, detail=''):
        self.stage.setText('阶段：' + text)
        self.detail.setText(detail)
        self.setVisible(True)

    def apply(self, info):
        stage = info.get('stage', '')
        done = info.get('done', 0)
        total = info.get('total', 0)
        speed = info.get('speed', 0)
        name = info.get('name', '')
        fd = info.get('files_done', 0)
        ft = info.get('files_total', 0)
        self.stage.setText('阶段：' + stage)
        if total > 0:
            pct = min(100.0, done * 100.0 / total)
            self.bar.setRange(0, 100)
            self.bar.setValue(int(pct))
            self.bar.setFormat('%.1f%%' % pct)
            amount = '已下载 %s / %s' % (fmt_size(done), fmt_size(total))
        else:
            self.bar.setRange(0, 0)
            amount = '已下载 %s / 计算中...' % fmt_size(done)
        parts = [amount, '速度 %s/s' % fmt_size(speed)]
        if ft:
            parts.append('文件 %d/%d' % (fd, ft))
        self.detail.setText('   ·   '.join(parts))
        if name:
            self.file.setText('当前：' + name)

    def finish(self, stage, detail=''):
        self.stage.setText('阶段：' + stage)
        self.detail.setText(detail)
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.bar.setFormat('100%')
        self.file.setText('')


class NavButton(QPushButton):
    def __init__(self, text, page_index, stack, parent=None):
        super().__init__(text, parent)
        self.page_index = page_index
        self.stack = stack
        self.setObjectName('NavButton')
        self.setCheckable(True)
        self.clicked.connect(self.activate)

    def activate(self):
        self.stack.setCurrentIndex(self.page_index)
        self.setChecked(True)


class TitleBar(QWidget):
    """PCL2 亮蓝顶栏：左侧 Logo + 居中导航胶囊 + 右侧窗口按钮。

    保留 min_btn / max_btn / close_btn 三个属性供 nativeEvent 与外部使用。
    拖动用 windowHandle().startSystemMove()（绕开 nativeEvent 返回值顺序坑）。
    """
    def __init__(self, parent, stack=None, nav_items=None, nav_group=None):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(50)
        self.setObjectName('TitleBar')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 0, 8, 0)
        layout.setSpacing(6)

        # ---- 左侧 Logo ----
        logo_box = QVBoxLayout()
        logo_box.setSpacing(0)
        logo_box.setContentsMargins(0, 0, 0, 0)
        self.logo = QLabel('PCL')
        self.logo.setObjectName('Logo')
        self.logo_sub = QLabel('Z MINECRAFT LAUNCHER')
        self.logo_sub.setObjectName('LogoSub')
        logo_box.addWidget(self.logo)
        logo_box.addWidget(self.logo_sub)
        layout.addLayout(logo_box)
        layout.addSpacing(18)
        layout.addStretch(1)

        # ---- 居中导航胶囊 ----
        self.nav_layout = QHBoxLayout()
        self.nav_layout.setSpacing(6)
        self.nav_buttons = []
        if stack is not None and nav_items:
            for text, idx in nav_items:
                btn = NavButton(text, idx, stack, self)
                self.nav_buttons.append(btn)
                if nav_group is not None:
                    nav_group.addButton(btn)
                self.nav_layout.addWidget(btn)
        layout.addLayout(self.nav_layout)
        layout.addStretch(1)

        # ---- 右侧窗口按钮 ----
        self.min_btn = QPushButton('—')
        self.max_btn = QPushButton('□')
        self.close_btn = QPushButton('✕')
        self.close_btn.setObjectName('close_btn')
        for b in (self.min_btn, self.max_btn, self.close_btn):
            b.setObjectName('WindowButton')
            b.setFixedHeight(30)
        self.close_btn.setObjectName('close_btn')  # 保持 hover 红色 + 窗口按钮基础样式
        self.min_btn.clicked.connect(parent.showMinimized)
        self.max_btn.clicked.connect(self.toggle_max)
        self.close_btn.clicked.connect(parent.close)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def paintEvent(self, event):
        """自绘顶栏蓝色渐变（透明父窗口下 QSS 渐变可能不生效）。"""
        from ui.styles import _palette
        theme = self.parent.app.settings.get('theme', 'light') if hasattr(self.parent, 'app') else 'light'
        c = _palette(theme)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(c['top1']))
        grad.setColorAt(1.0, QColor(c['top2']))
        p.fillRect(QRectF(self.rect()), QBrush(grad))

    def toggle_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            child = self.childAt(e.pos())
            if child in (self.min_btn, self.max_btn, self.close_btn) or isinstance(child, NavButton):
                return
            wh = self.parent.windowHandle()
            if wh is not None:
                wh.startSystemMove()
            e.accept()


class LaunchButton(QPushButton):
    def __init__(self, text='启动游戏', parent=None):
        super().__init__(text, parent)
        self.setObjectName('LaunchButton')


class Card(QFrame):
    """通用的圆角卡片容器，内部直接往 layout 里加控件即可。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('Card')
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(18, 16, 18, 16)
        self._lay.setSpacing(10)

    def box(self):
        return self._lay


class PrimaryButton(QPushButton):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setObjectName('PrimaryButton')


class GhostButton(QPushButton):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setObjectName('GhostButton')
