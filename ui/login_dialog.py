import webbrowser
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QFrame, QMessageBox, QApplication)
from PyQt5.QtCore import pyqtSignal

from core.auth import (create_offline, microsoft_device_code, microsoft_login_flow,
                       save_account, CLIENT_ID)
from ui.worker import Worker


class LoginDialog(QDialog):
    account_ready = pyqtSignal(dict)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle('登录账号')
        self.setMinimumSize(440, 340)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        t = QLabel('离线账号')
        t.setObjectName('PageTitle')
        layout.addWidget(t)
        row = QHBoxLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName('LineEdit')
        self.name_edit.setPlaceholderText('输入游戏名（最多 16 字符）')
        self.off_btn = QPushButton('离线登录')
        self.off_btn.setObjectName('PrimaryButton')
        self.off_btn.clicked.connect(self.do_offline)
        row.addWidget(self.name_edit, 1)
        row.addWidget(self.off_btn)
        layout.addLayout(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName('Sep')
        layout.addWidget(sep)

        t2 = QLabel('微软正版账号')
        t2.setObjectName('PageTitle')
        layout.addWidget(t2)
        self.ms_btn = QPushButton('微软正版登录')
        self.ms_btn.setObjectName('PrimaryButton')
        self.ms_btn.clicked.connect(self.start_ms)
        layout.addWidget(self.ms_btn)

        self.code_lbl = QLabel('')
        self.code_lbl.setObjectName('CodeLabel')
        layout.addWidget(self.code_lbl)
        self.url_lbl = QLabel('')
        self.url_lbl.setObjectName('UrlLabel')
        self.url_lbl.setWordWrap(True)
        layout.addWidget(self.url_lbl)
        self.status_lbl = QLabel('')
        self.status_lbl.setObjectName('PageHint')
        self.status_lbl.setWordWrap(True)
        layout.addWidget(self.status_lbl)
        layout.addStretch(1)

    def _show_err(self, msg):
        self.status_lbl.setText('出错了:\n' + msg)
        QMessageBox.warning(self, '登录失败', msg)

    def do_offline(self):
        name = self.name_edit.text().strip() or 'Steve'
        acc = create_offline(name)
        save_account(self.app.data_root, acc)
        self.app.refresh_accounts()
        self.account_ready.emit(acc)
        self.accept()

    def start_ms(self):
        cid = self.app.settings.get('msaClientId') or CLIENT_ID
        try:
            dc = microsoft_device_code(cid)
        except Exception as e:
            self._show_err('获取设备码失败: ' + str(e))
            return
        code = dc['user_code']
        uri = dc['verification_uri']
        self.code_lbl.setText('验证码（已复制）: ' + code)
        self.url_lbl.setText('登录网址: ' + uri)
        try:
            QApplication.clipboard().setText(code)
            webbrowser.open(uri)
            self.status_lbl.setText('验证码已自动复制到剪贴板，并已用默认浏览器打开登录页。\n请在浏览器中登录并授权，本窗口将自动完成...')
        except Exception as e:
            self.status_lbl.setText('已获取验证码，但自动打开/复制失败: ' + str(e) + '\n请手动打开: ' + uri + ' 并输入: ' + code)
        self.ms_btn.setEnabled(False)
        self.off_btn.setEnabled(False)

        def job():
            return microsoft_login_flow(dc, cid)

        w = Worker(job)
        self._ms_worker = w
        w.done.connect(self.on_done)
        w.error.connect(lambda e: self._show_err('登录失败: ' + e))
        w.finished.connect(w.deleteLater)
        w.start()

    def on_done(self, acc):
        save_account(self.app.data_root, acc)
        self.app.refresh_accounts()
        self.account_ready.emit(acc)
        self.accept()
