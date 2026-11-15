# -*- coding: utf-8 -*-
"""PCL 风格的基础控件。

保留旧页面层依赖的接口：
- fmt_size(n)
- ProgressPanel(QFrame)        对象名 Card / CardTitle / ProgressBar / CardSub / PageHint
- TitleBar(QWidget)            含 min_btn / max_btn / close_btn，拖动用 startSystemMove
- NavButton(QPushButton)       侧边栏导航按钮
并新增 Card / PrimaryButton / GhostButton 等便捷控件。
"""
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
                             QFrame, QProgressBar)
from PyQt5.QtCore import Qt


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


class TitleBar(QWidget):
    def __init__(self, parent, title='Z MINECRAFT LAUNCHER'):
        super().__init__(parent)
        self.parent = parent
        self.setFixedHeight(40)
        self.setObjectName('TitleBar')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 8, 0)
        layout.setSpacing(8)
        self.icon = QLabel('◆')
        self.icon.setObjectName('TitleIcon')
        self.title = QLabel(title)
        self.title.setObjectName('TitleText')
        layout.addWidget(self.icon)
        layout.addWidget(self.title)
        layout.addStretch(1)
        self.min_btn = QPushButton('—')
        self.max_btn = QPushButton('▢')
        self.close_btn = QPushButton('✕')
        for b in (self.min_btn, self.max_btn, self.close_btn):
            b.setObjectName('WindowButton')
            b.setFixedSize(36, 28)
        self.min_btn.clicked.connect(parent.showMinimized)
        self.max_btn.clicked.connect(self.toggle_max)
        self.close_btn.clicked.connect(parent.close)
        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def toggle_max(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            child = self.childAt(e.pos())
            if child in (self.min_btn, self.max_btn, self.close_btn):
                return
            wh = self.parent.windowHandle()
            if wh is not None:
                wh.startSystemMove()
            e.accept()


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
