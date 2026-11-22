# -*- coding: utf-8 -*-
"""PCL2 风格主窗口外壳。

布局（对齐 PCL2 官方界面）：
  - 顶部：亮蓝标题栏，左侧 PCL Logo、居中导航胶囊、右侧窗口按钮。
  - 左侧：白色账号栏，顶部「正版 / 离线」标签、头像、账号列表与登录按钮，
          底部「启动游戏」大按钮 + 版本选择 / 版本设置。
  - 右侧：浅蓝渐变主内容区，白色圆角卡片承载功能页面。

交互沿用已调好的方案：标题栏拖动用 startSystemMove；八方向缩放在 nativeEvent
处理 WM_NCHITTEST（返回 (handled, result)）；切页用纯几何滑动，不用透明度效果发白。
保留 app.py / 页面层依赖的全部接口。
"""
import ctypes

from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
                             QLabel, QButtonGroup, QPushButton, QListWidget,
                             QListWidgetItem, QSpacerItem, QSizePolicy)
from PyQt5.QtCore import Qt, QPoint, QRectF, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QRegion, QPainter, QColor, QPen, QPainterPath, QBrush, QLinearGradient

from ui.widgets import TitleBar, NavButton, LaunchButton
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
        self.setMinimumSize(980, 620)
        self.resize(1160, 740)
        self.setObjectName('MainWindow')
        self.setWindowTitle('Z MINECRAFT LAUNCHER')
        self._setup_ui()
        self.update_account_label()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 页面栈（先建，顶栏导航要用）
        self.stack = QStackedWidget()
        self.stack.setObjectName('MainArea')
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

        nav_items = [('▶  启动', 0), ('◇  版本', 1), ('▦  模组', 2),
                     ('⚙  设置', 3), ('⊞  更多', 4)]
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        # 顶部蓝色导航栏
        self.title_bar = TitleBar(self, stack=self.stack,
                                  nav_items=nav_items, nav_group=self.nav_group)
        root.addWidget(self.title_bar)

        # 下半部分：左侧账号栏 + 右侧内容区
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar(), 0)
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        self.nav_group.buttons()[0].setChecked(True)

    def _build_sidebar(self):
        side = QWidget()
        side.setObjectName('SideBar')
        side.setFixedWidth(166)
        sb = QVBoxLayout(side)
        sb.setContentsMargins(18, 22, 18, 16)
        sb.setSpacing(8)

        # 正版 / 离线 标签
        tag_row = QHBoxLayout()
        tag_row.setSpacing(8)
        self.tag_official = QLabel('正版')
        self.tag_official.setObjectName('AccountTag')
        self.tag_offline = QLabel('离线')
        self.tag_offline.setObjectName('AccountTagInactive')
        tag_row.addWidget(self.tag_official)
        tag_row.addWidget(self.tag_offline)
        tag_row.addStretch(1)
        sb.addLayout(tag_row)
        sb.addSpacing(18)

        # 头像
        self.avatar = QLabel('☺')
        self.avatar.setObjectName('Avatar')
        self.avatar.setAlignment(Qt.AlignCenter)
        sb.addWidget(self.avatar)
        sb.addSpacing(6)

        # 当前账号
        self.account_label = QLabel('未登录')
        self.account_label.setObjectName('AccountLabel')
        self.account_label.setAlignment(Qt.AlignCenter)
        self.account_label.setWordWrap(True)
        sb.addWidget(self.account_label)

        # 账号列表（下拉样式）
        self.account_list = QListWidget()
        self.account_list.setObjectName('AccountList')
        self.account_list.setFixedHeight(64)
        self.account_list.currentItemChanged.connect(self._on_account_pick)
        self.account_list.itemDoubleClicked.connect(lambda _: self._switch_account())
        sb.addWidget(self.account_list)

        acc_row = QHBoxLayout()
        acc_row.setSpacing(6)
        self.login_btn = QPushButton('登录')
        self.login_btn.setObjectName('ThemeButton')
        self.login_btn.clicked.connect(self.open_login)
        self.switch_btn = QPushButton('切换')
        self.switch_btn.setObjectName('ThemeButton')
        self.switch_btn.clicked.connect(self._switch_account)
        self.refresh_acc_btn = QPushButton('刷新')
        self.refresh_acc_btn.setObjectName('ThemeButton')
        self.refresh_acc_btn.setToolTip('刷新当前账号的令牌与角色资料（皮肤等）')
        self.refresh_acc_btn.clicked.connect(self._refresh_account)
        acc_row.addWidget(self.login_btn)
        acc_row.addWidget(self.switch_btn)
        acc_row.addWidget(self.refresh_acc_btn)
        sb.addLayout(acc_row)

        self.manage_btn = QPushButton('账号管理')
        self.manage_btn.setObjectName('ThemeButton')
        self.manage_btn.clicked.connect(self.open_accounts)
        sb.addWidget(self.manage_btn)

        sb.addSpacerItem(QSpacerItem(0, 12, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # 左下「启动游戏」大按钮（PCL2 标志性元素）
        self.launch_btn = LaunchButton('▶  启动游戏')
        self.launch_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        sb.addWidget(self.launch_btn)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        ver_btn = QPushButton('版本选择')
        ver_btn.setObjectName('ThemeButton')
        ver_btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        set_btn = QPushButton('版本设置')
        set_btn.setObjectName('ThemeButton')
        set_btn.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        quick_row.addWidget(ver_btn)
        quick_row.addWidget(set_btn)
        sb.addLayout(quick_row)

        self.theme_btn = QPushButton('◐  切换主题')
        self.theme_btn.setObjectName('ThemeButton')
        self.theme_btn.clicked.connect(self._toggle_theme)
        sb.addWidget(self.theme_btn)
        return side

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
            # 账号类型标签随当前账号切换
            cur_type = (self.app.current_account or {}).get('type', 'offline')
            official = cur_type not in ('offline',)
            self.tag_official.setObjectName('AccountTag' if official else 'AccountTagInactive')
            self.tag_offline.setObjectName('AccountTag' if not official else 'AccountTagInactive')
            self.tag_official.style().polish(self.tag_official)
            self.tag_offline.style().polish(self.tag_offline)
        finally:
            self.account_list.blockSignals(False)

    def _on_account_pick(self, cur, prev):
        if not cur:
            return
        uid = cur.data(Qt.UserRole)
        if (self.app.current_account or {}).get('uuid') == uid:
            self.account_label.setText(cur.text().lstrip('● ').split('（')[0])
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
        self._toast.move(g.x() + (g.width() - self._toast.width()) // 2, g.y() + 60)
        self._toast.show()

    def update_account_label(self):
        acc = self.app.current_account
        if acc:
            from core.account import account_label
            self.account_label.setText(account_label(acc))
        else:
            self.account_label.setText('未登录')
        if hasattr(self, 'account_list'):
            self.refresh_account_list()

    def _toggle_theme(self):
        cur = self.app.get_settings().get('theme', 'light')
        self.app.set_theme('dark' if cur == 'light' else 'light')
        self.update()

    def _on_page_changed(self, index):
        if not self.isVisible():
            return
        w = self.stack.widget(index)
        if w is None:
            return
        # 纯几何滑动：从下方 10px 滑入，不使用透明度效果（避免透明父窗口发白）。
        anim = QPropertyAnimation(w, b'pos')
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(QPoint(0, 10))
        anim.setEndValue(QPoint(0, 0))
        anim.start()

    # ---- 圆角窗口背景：顶栏蓝 + 主区浅蓝渐变（WA_TranslucentBackground 下自绘） ----
    def paintEvent(self, event):
        from ui.styles import get_window_colors
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 12, 12)
        top, bottom = get_window_colors(self.app.settings.get('theme', 'light'))
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(top))
        grad.setColorAt(1.0, QColor(bottom))
        p.fillPath(path, QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawPath(path)

    def _apply_mask(self):
        if self.isMaximized():
            self.clearMask()
        else:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), 12, 12)
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_mask()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_mask()

    # ---- 无边框窗口八方向缩放 ----
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
