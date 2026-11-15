# -*- coding: utf-8 -*-
"""PCL 风格的主窗口外壳。

左侧导航栏 + 右侧多页面；无边框圆角；标题栏拖动用 startSystemMove；
窗口八方向缩放用 WM_NCHITTEST（返回顺序 (handled, result)，去掉会整段
跳过的 eventType 守卫）；切页用纯几何滑动，不再用 QGraphicsOpacityEffect 发白。
保留 app.py / 页面层依赖的接口：update_account_label / show_toast / pages /
title_bar(min/max/close) / open_login / open_accounts / refresh_account_list ...
"""
import ctypes

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
                             QLabel, QButtonGroup, QPushButton, QListWidget,
                             QListWidgetItem, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt, QPoint, QRectF, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QRegion, QPainter, QColor, QPen, QPainterPath

from ui.widgets import TitleBar, NavButton
from ui.instances_page import InstancesPage
from ui.version_page import VersionPage
from ui.settings_page import SettingsPage
from ui.manual_page import ManualPage
from ui.login_dialog import LoginDialog
from ui.account_dialog import AccountDialog
from ui.toast import Toast
from ui.mod_page import ModPage


class MainWindow(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(960, 620)
        self.resize(1120, 720)
        self.setObjectName('MainWindow')
        self.setWindowTitle('Z MINECRAFT LAUNCHER')
        self._setup_ui()
        self.update_account_label()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.title_bar = TitleBar(self)
        root.addWidget(self.title_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName('SideBar')
        self.sidebar.setFixedWidth(220)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(14, 20, 14, 18)
        sb.setSpacing(8)

        brand = QLabel('Z MINECRAFT')
        brand.setObjectName('Brand')
        sb.addWidget(brand)
        sub = QLabel('LAUNCHER')
        sub.setObjectName('Brand')
        sb.addWidget(sub)
        sb.addSpacing(12)

        self.stack = QStackedWidget()
        self.stack.currentChanged.connect(self._on_page_changed)
        self.pages = [
            InstancesPage(self.app),
            VersionPage(self.app),
            ModPage(self.app),
            SettingsPage(self.app),
            ManualPage(self.app),
        ]
        for p in self.pages:
            self.stack.addWidget(p)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        nav_items = [('启动', 0), ('版本', 1), ('模组', 2), ('设置', 3), ('说明书', 4)]
        for text, idx in nav_items:
            btn = NavButton(text, idx, self.stack)
            self.nav_group.addButton(btn)
            sb.addWidget(btn)
        sb.addSpacing(12)

        self.account_label = QLabel('未登录')
        self.account_label.setObjectName('AccountLabel')
        sb.addWidget(self.account_label)

        self.account_list = QListWidget()
        self.account_list.setObjectName('AccountList')
        self.account_list.setFixedHeight(112)
        self.account_list.currentItemChanged.connect(self._on_account_pick)
        self.account_list.itemDoubleClicked.connect(lambda _: self._switch_account())
        sb.addWidget(self.account_list)

        acc_row = QHBoxLayout()
        acc_row.setSpacing(6)
        self.login_btn = QPushButton('登录')
        self.login_btn.setObjectName('ThemeButton')
        self.login_btn.clicked.connect(self.open_login)
        acc_row.addWidget(self.login_btn)

        self.switch_btn = QPushButton('切换')
        self.switch_btn.setObjectName('ThemeButton')
        self.switch_btn.clicked.connect(self._switch_account)
        acc_row.addWidget(self.switch_btn)

        self.refresh_acc_btn = QPushButton('刷新')
        self.refresh_acc_btn.setObjectName('ThemeButton')
        self.refresh_acc_btn.setToolTip('刷新当前账号的令牌与角色资料（皮肤等）')
        self.refresh_acc_btn.clicked.connect(self._refresh_account)
        acc_row.addWidget(self.refresh_acc_btn)
        sb.addLayout(acc_row)

        self.manage_btn = QPushButton('账号管理')
        self.manage_btn.setObjectName('ThemeButton')
        self.manage_btn.clicked.connect(self.open_accounts)
        sb.addWidget(self.manage_btn)

        sb.addSpacerItem(QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))

        theme_btn = QPushButton('切换主题')
        theme_btn.setObjectName('ThemeButton')
        theme_btn.clicked.connect(self._toggle_theme)
        sb.addWidget(theme_btn)

        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        self.nav_group.buttons()[0].setChecked(True)

    def open_login(self):
        dlg = LoginDialog(self.app, self)
        dlg.account_ready.connect(self.app.set_current_account)
        dlg.account_ready.connect(
            lambda acc: self.show_toast('登录成功，账号：' + acc['name'], 'success'))
        dlg.exec_()

    def open_accounts(self):
        dlg = AccountDialog(self.app, self)
        dlg.account_switched.connect(
            lambda acc: self.show_toast('已切换账号：' + acc['name'], 'success'))
        dlg.exec_()
        self.refresh_account_list()

    def refresh_account_list(self):
        from core.account import account_label
        cur_uid = (self.app.current_account or {}).get('uuid')
        cur_row = -1
        self.account_list.blockSignals(True)
        try:
            self.account_list.clear()
            for acc in self.app.accounts:
                it = QListWidgetItem(account_label(acc))
                it.setData(Qt.UserRole, acc.get('uuid'))
                if acc.get('uuid') == cur_uid:
                    it.setText('● ' + it.text())
                    cur_row = self.account_list.count()
                self.account_list.addItem(it)
            if cur_row >= 0:
                self.account_list.setCurrentRow(cur_row)
            elif self.account_list.count():
                self.account_list.setCurrentRow(0)
        finally:
            self.account_list.blockSignals(False)

    def _on_account_pick(self, cur, prev):
        if not cur:
            return
        uid = cur.data(Qt.UserRole)
        if (self.app.current_account or {}).get('uuid') == uid:
            self.account_label.setText('当前账号: ' + cur.text().lstrip('● ').split('（')[0])
            return
        for a in self.app.accounts:
            if a.get('uuid') == uid:
                self.app.set_current_account(a)
                self.refresh_account_list()
                self.show_toast('已切换账号：' + a.get('name', ''), 'success')
                return

    def _switch_account(self):
        it = self.account_list.currentItem()
        if not it:
            self.show_toast('请先在列表中选择账号', 'error')
            return
        uid = it.data(Qt.UserRole)
        for a in self.app.accounts:
            if a.get('uuid') == uid:
                self.app.set_current_account(a)
                self.refresh_account_list()
                self.show_toast('已切换账号：' + a.get('name', ''), 'success')
                return

    def _refresh_account(self):
        from core.auth import save_account
        from ui.worker import Worker
        from core.account import refresh_account
        acc = self.app.current_account
        if not acc:
            self.show_toast('请先登录账号', 'error')
            return
        if acc.get('type') == 'offline':
            self.show_toast('离线账号无需刷新', 'error')
            return
        self.show_toast('正在刷新 ' + acc.get('name', '') + ' ...', 'info')

        def job():
            return refresh_account(acc, self.app.settings.get('msaClientId') or None)

        w = Worker(job)
        self._refresh_worker = w
        w.done.connect(self._on_refresh_done)
        w.error.connect(lambda e: self.show_toast('刷新失败：' + str(e), 'error'))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_refresh_done(self, new_acc):
        from core.auth import save_account
        save_account(self.app.data_root, new_acc)
        self.app.refresh_accounts()
        self.refresh_account_list()
        self.show_toast('账号已刷新：' + new_acc.get('name', ''), 'success')

    def show_toast(self, text, kind='success'):
        self._toast = Toast(self, text, kind)
        g = self.geometry()
        self._toast.move(g.x() + (g.width() - self._toast.width()) // 2, g.y() + 18)
        self._toast.show()

    def update_account_label(self):
        acc = self.app.current_account
        if acc:
            from core.account import account_label
            self.account_label.setText('当前账号: ' + account_label(acc))
        else:
            self.account_label.setText('未登录')
        if hasattr(self, 'account_list'):
            self.refresh_account_list()

    def _toggle_theme(self):
        cur = self.app.get_settings().get('theme', 'dark')
        self.app.set_theme('light' if cur == 'dark' else 'dark')

    def _on_page_changed(self, index):
        if not self.isVisible():
            return
        w = self.stack.widget(index)
        if w is None:
            return
        # 纯几何滑动：从下方 12px 滑入。不使用透明度效果，避免透明父窗口发白。
        anim = QPropertyAnimation(w, b'pos')
        anim.setDuration(170)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(QPoint(0, 12))
        anim.setEndValue(QPoint(0, 0))
        anim.start()

    # ---- 圆角窗口背景（WA_TranslucentBackground 下必须自绘） ----
    def paintEvent(self, event):
        from ui.styles import get_bg
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = get_bg(self.app.settings.get('theme', 'dark'))
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.fillPath(path, QColor(bg))
        p.setPen(QPen(QColor(255, 255, 255, 22 if bg.startswith('#1') else 70), 1))
        p.drawPath(path)

    # ---- 圆角遮罩：随窗口尺寸 / 最大化状态刷新 ----
    def _apply_mask(self):
        if self.isMaximized():
            self.clearMask()
        else:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 14, 14)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_mask()

    # ---- 无边框窗口的八方向缩放：处理 WM_NCHITTEST ----
    def nativeEvent(self, eventType, message):
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                g = self.frameGeometry()
                lx, ly = x - g.x(), y - g.y()
                w, h = g.width(), g.height()
                EDGE = 8
                # 标题栏区域交给 TitleBar 的 startSystemMove 处理拖动
                if ly < self.title_bar.height():
                    return super().nativeEvent(eventType, message)
                if not self.isMaximized():
                    if lx < EDGE and ly > h - EDGE:
                        return True, 16   # HTBOTTOMLEFT
                    if lx > w - EDGE and ly > h - EDGE:
                        return True, 17   # HTBOTTOMRIGHT
                    if lx < EDGE:
                        return True, 10   # HTLEFT
                    if lx > w - EDGE:
                        return True, 11   # HTRIGHT
                    if ly > h - EDGE:
                        return True, 15   # HTBOTTOM
        except Exception:
            pass
        return super().nativeEvent(eventType, message)
