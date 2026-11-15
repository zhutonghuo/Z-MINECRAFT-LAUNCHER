# -*- coding: utf-8 -*-
"""账号管理对话框。

功能：
  - 列出所有已登录账号，点击即可切换（无需重复登录）
  - 「刷新」按钮：主动更新 accessToken 与角色资料（解决登录后同步延迟大的问题）
  - 新增第三方登录服务器（Yggdrasil / authlib-injector 规范）账号
  - 删除账号
"""
import webbrowser

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QFrame, QMessageBox, QApplication,
                             QListWidget, QListWidgetItem, QComboBox, QTabWidget,
                             QWidget)

from core.account import account_label, refresh_account
from core.auth import (CLIENT_ID, create_offline, microsoft_device_code,
                       microsoft_login_flow, save_account, ygg_authenticate)
from ui.worker import Worker


class AccountDialog(QDialog):
    """账号列表 + 切换 + 刷新"""
    account_switched = pyqtSignal(dict)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle('账号管理')
        self.setMinimumSize(520, 520)
        self.setObjectName('Page')
        self._worker = None
        self._build()
        # 打开对话框时立即填充账号列表，否则列表永远是空的
        self.refresh_list()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        t = QLabel('已登录账号')
        t.setObjectName('PageTitle')
        lay.addWidget(t)

        self.list_w = QListWidget()
        self.list_w.setObjectName('AccountList')
        self.list_w.currentItemChanged.connect(self._on_select)
        self.list_w.itemDoubleClicked.connect(lambda _: self._switch())
        lay.addWidget(self.list_w, 1)

        row = QHBoxLayout()
        self.use_btn = QPushButton('使用此账号')
        self.use_btn.setObjectName('PrimaryButton')
        self.use_btn.clicked.connect(self._switch)
        row.addWidget(self.use_btn)

        self.refresh_btn = QPushButton('刷新账号')
        self.refresh_btn.setObjectName('ThemeButton')
        self.refresh_btn.clicked.connect(self._refresh)
        row.addWidget(self.refresh_btn)

        self.del_btn = QPushButton('删除')
        self.del_btn.setObjectName('ThemeButton')
        self.del_btn.clicked.connect(self._delete)
        row.addWidget(self.del_btn)
        lay.addLayout(row)

        self.status = QLabel('')
        self.status.setObjectName('PageHint')
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName('Sep')
        lay.addWidget(sep)

        t2 = QLabel('添加账号')
        t2.setObjectName('PageTitle')
        lay.addWidget(t2)

        tabs = QTabWidget()
        tabs.setObjectName('Tabs')
        tabs.addTab(self._tab_microsoft(), '微软正版')
        tabs.addTab(self._tab_yggdrasil(), '第三方服务器')
        tabs.addTab(self._tab_offline(), '离线账号')
        lay.addWidget(tabs)

    # ------------------------------------------------------------ 微软正版
    def _tab_microsoft(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        self.ms_code = QLabel('')
        self.ms_code.setObjectName('CodeLabel')
        v.addWidget(self.ms_code)
        self.ms_url = QLabel('')
        self.ms_url.setObjectName('UrlLabel')
        self.ms_url.setWordWrap(True)
        v.addWidget(self.ms_url)
        self.ms_status = QLabel('')
        self.ms_status.setObjectName('PageHint')
        self.ms_status.setWordWrap(True)
        v.addWidget(self.ms_status)
        btn = QPushButton('获取验证码并登录')
        btn.setObjectName('PrimaryButton')
        btn.clicked.connect(self._start_ms)
        v.addWidget(btn)
        v.addStretch(1)
        return w

    # ------------------------------------------------------------ 第三方服务器
    def _tab_yggdrasil(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)

        self.srv_edit = QLineEdit()
        self.srv_edit.setObjectName('LineEdit')
        self.srv_edit.setPlaceholderText('登录服务器地址，如 https://littleskin.cn/api/yggdrasil')
        self.srv_edit.setText(self.app.settings.get('yggServer', ''))
        v.addWidget(QLabel('服务器地址'))
        v.addWidget(self.srv_edit)

        self.srv_combo = QComboBox()
        self.srv_combo.setObjectName('ComboBox')
        self.srv_combo.addItem('使用上面填写的地址', '')
        for name, url in (self.app.settings.get('yggServers') or {}).items():
            self.srv_combo.addItem(name, url)
        self.srv_combo.currentIndexChanged.connect(self._on_srv_pick)
        v.addWidget(self.srv_combo)

        self.ygg_user = QLineEdit()
        self.ygg_user.setObjectName('LineEdit')
        self.ygg_user.setPlaceholderText('用户名')
        v.addWidget(self.ygg_user)

        self.ygg_pass = QLineEdit()
        self.ygg_pass.setObjectName('LineEdit')
        self.ygg_pass.setPlaceholderText('密码')
        self.ygg_pass.setEchoMode(QLineEdit.Password)
        v.addWidget(self.ygg_pass)

        self.ygg_status = QLabel('')
        self.ygg_status.setObjectName('PageHint')
        self.ygg_status.setWordWrap(True)
        v.addWidget(self.ygg_status)

        btn = QPushButton('登录第三方服务器')
        btn.setObjectName('PrimaryButton')
        btn.clicked.connect(self._start_ygg)
        v.addWidget(btn)
        v.addStretch(1)
        return w

    def _on_srv_pick(self, idx):
        url = self.srv_combo.itemData(idx) if idx >= 0 else ''
        if url:
            self.srv_edit.setText(url)

    # ------------------------------------------------------------ 离线
    def _tab_offline(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        self.off_name = QLineEdit()
        self.off_name.setObjectName('LineEdit')
        self.off_name.setPlaceholderText('游戏名（最多 16 字符）')
        v.addWidget(self.off_name)
        btn = QPushButton('创建离线账号')
        btn.setObjectName('PrimaryButton')
        btn.clicked.connect(self._do_offline)
        v.addWidget(btn)
        v.addStretch(1)
        return w

    # ------------------------------------------------------------ 行为
    def refresh_list(self):
        """重载账号列表"""
        self.app.refresh_accounts()
        cur = self.list_w.currentItem()
        keep = cur.text() if cur else None
        cur_uid = (self.app.current_account or {}).get('uuid')
        cur_row = -1
        # 整个重建过程屏蔽信号，避免 setCurrentRow 触发 _on_select/_switch 造成递归
        self.list_w.blockSignals(True)
        try:
            self.list_w.clear()
            for acc in self.app.accounts:
                it = QListWidgetItem(account_label(acc))
                it.setData(Qt.UserRole, acc.get('uuid'))
                if acc.get('uuid') == cur_uid:
                    it.setText('● ' + it.text())
                    cur_row = self.list_w.count()
                self.list_w.addItem(it)
                if keep and it.text().endswith(keep):
                    self.list_w.setCurrentItem(it)
            # 高亮指向真正的当前账号，避免与实际启动用的账号不一致
            if cur_row >= 0:
                self.list_w.setCurrentRow(cur_row)
            elif self.list_w.currentItem() is None and self.list_w.count():
                self.list_w.setCurrentRow(0)
        finally:
            self.list_w.blockSignals(False)

    def _on_select(self, cur, prev):
        acc = self._current_account()
        if not acc:
            return
        t = acc.get('type')
        if t == 'microsoft':
            self.status.setText('微软正版账号 %s\nUUID: %s' % (acc.get('name'), acc.get('uuid')))
        elif t == 'yggdrasil':
            self.status.setText('第三方账号 %s\n服务器: %s\nUUID: %s' % (
                acc.get('name'), acc.get('server'), acc.get('uuid')))
        else:
            self.status.setText('离线账号 %s\nUUID: %s' % (acc.get('name'), acc.get('uuid')))

    def _current_account(self):
        it = self.list_w.currentItem()
        if not it:
            return None
        uid = it.data(Qt.UserRole)
        for a in self.app.accounts:
            if a.get('uuid') == uid:
                return a
        return None

    def _switch(self):
        acc = self._current_account()
        if not acc:
            return
        self.app.set_current_account(acc)
        self.account_switched.emit(acc)
        self.status.setText('已切换到：' + account_label(acc))
        self.refresh_list()

    def _delete(self):
        acc = self._current_account()
        if not acc:
            return
        if QMessageBox.question(self, '删除账号',
                                '确定要删除账号 %s 吗？\n（下次启动游戏需要重新登录）'
                                % acc.get('name')) != QMessageBox.Yes:
            return
        import os
        from core.auth import accounts_dir
        p = os.path.join(accounts_dir(self.app.data_root), acc.get('uuid') + '.json')
        try:
            if os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
        self.refresh_list()
        self.status.setText('已删除账号 ' + acc.get('name'))

    def _refresh(self):
        """主动刷新账号令牌与资料"""
        acc = self._current_account()
        if not acc:
            self.status.setText('请先在列表里选择一个账号')
            return
        if acc.get('type') == 'offline':
            self.status.setText('离线账号无需刷新')
            return
        self.status.setText('正在刷新 %s ...' % acc.get('name'))
        QApplication.processEvents()

        def job():
            return refresh_account(acc, self.app.settings.get('msaClientId') or None)

        w = Worker(job)
        self._worker = w
        w.done.connect(self._on_refreshed)
        w.error.connect(lambda e: self.status.setText('刷新失败：' + str(e)))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_refreshed(self, new_acc):
        save_account(self.app.data_root, new_acc)
        self.app.refresh_accounts()
        self.refresh_list()
        self.status.setText('已刷新 %s，令牌与资料已更新' % new_acc.get('name'))

    def _start_ms(self):
        cid = self.app.settings.get('msaClientId') or CLIENT_ID
        try:
            dc = microsoft_device_code(cid)
        except Exception as e:
            self.ms_status.setText('获取设备码失败: ' + str(e))
            return
        code = dc['user_code']
        uri = dc['verification_uri']
        self.ms_code.setText('验证码（已复制）: ' + code)
        self.ms_url.setText('登录网址: ' + uri)
        try:
            QApplication.clipboard().setText(code)
            webbrowser.open(uri)
            self.ms_status.setText('验证码已复制，浏览器已打开登录页，请完成授权...')
        except Exception as e:
            self.ms_status.setText('请手动打开 %s 并输入 %s (%s)' % (uri, code, e))

        def job():
            return microsoft_login_flow(dc, cid)

        w = Worker(job)
        self._worker = w
        w.done.connect(self._on_ms_done)
        w.error.connect(lambda e: self.ms_status.setText('登录失败: ' + str(e)))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_ms_done(self, acc):
        save_account(self.app.data_root, acc)
        self.app.refresh_accounts()
        self.refresh_list()
        self.app.set_current_account(acc)
        self.account_switched.emit(acc)
        self.ms_status.setText('登录成功：' + acc['name'])
        self.status.setText('已登录并选中 ' + account_label(acc))

    def _start_ygg(self):
        server = self.srv_edit.text().strip().rstrip('/')
        if not server:
            self.ygg_status.setText('请填写登录服务器地址')
            return
        if not server.startswith('http'):
            server = 'https://' + server
        user = self.ygg_user.text().strip()
        pwd = self.ygg_pass.text()
        if not user or not pwd:
            self.ygg_status.setText('请填写用户名和密码')
            return
        self.ygg_status.setText('正在登录 %s ...' % server)

        def job():
            return ygg_authenticate(server, user, pwd)

        w = Worker(job)
        self._worker = w
        w.done.connect(self._on_ygg_done)
        w.error.connect(lambda e: self.ygg_status.setText('登录失败: ' + str(e)))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_ygg_done(self, acc):
        save_account(self.app.data_root, acc)
        # 记住服务器地址，方便下次直接选
        s = self.app.settings
        s['yggServer'] = acc.get('server', '')
        servers = dict(s.get('yggServers') or {})
        host = acc.get('server', '').split('//')[-1].split('/')[0]
        if host:
            servers[host] = acc.get('server')
        s['yggServers'] = servers
        self.app.save_settings()
        self.app.refresh_accounts()
        self.refresh_list()
        self.app.set_current_account(acc)
        self.account_switched.emit(acc)
        self.ygg_status.setText('登录成功：' + acc['name'])

    def _do_offline(self):
        name = self.off_name.text().strip() or 'Steve'
        acc = create_offline(name)
        save_account(self.app.data_root, acc)
        self.app.refresh_accounts()
        self.refresh_list()
        self.app.set_current_account(acc)
        self.account_switched.emit(acc)
        self.status.setText('已创建并选中 ' + account_label(acc))
