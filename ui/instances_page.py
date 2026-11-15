import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QDialog, QLineEdit, QComboBox,
                             QMessageBox, QMenu, QAction)

from core.instances import list_instances, delete_instance, create_instance
from core.installer import is_installed
from ui.login_dialog import LoginDialog


class InstanceCard(QFrame):
    def __init__(self, instance, page):
        super().__init__()
        self.instance = instance
        self.page = page
        self.setObjectName('Card')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        info = QVBoxLayout()
        info.setSpacing(4)
        name = QLabel(instance['name'])
        name.setObjectName('CardTitle')
        sub = QLabel('版本 %s · %s' % (instance['versionId'], instance.get('modLoader', 'vanilla')))
        sub.setObjectName('CardSub')
        info.addWidget(name)
        info.addWidget(sub)
        layout.addLayout(info, 1)
        self.play_btn = QPushButton('启动')
        self.play_btn.setObjectName('PlayButton')
        self.play_btn.clicked.connect(self.play)
        self.del_btn = QPushButton('删除')
        self.del_btn.setObjectName('GhostButton')
        self.del_btn.clicked.connect(self.remove)
        layout.addWidget(self.play_btn)
        layout.addWidget(self.del_btn)
        self.setAcceptDrops(True)

    def play(self):
        app = self.page.app
        if not app.current_account:
            dlg = LoginDialog(app, self.page)
            dlg.account_ready.connect(app.set_current_account)
            if dlg.exec_() != QDialog.Accepted:
                return
        app.launch_instance(self.instance)

    def remove(self):
        r = QMessageBox.question(self.page, '删除实例',
                                 '确定删除实例「%s」？此操作不可恢复。' % self.instance['name'],
                                 QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            delete_instance(self.page.app.data_root, self.instance['name'])
            self.page.refresh()

    # ---------------------------------------------------------- 右键菜单
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        a = QAction('实例设置', self)
        a.triggered.connect(lambda: self.page.open_settings(self.instance))
        menu.addAction(a)
        menu.addSeparator()
        for label, sub in [('打开版本文件夹', ''), ('打开 Mod 文件夹', 'mods'),
                           ('打开资源包文件夹', 'resourcepacks'),
                           ('打开光影文件夹', 'shaderpacks'),
                           ('打开世界文件夹', 'saves')]:
            act = QAction(label, self)
            act.triggered.connect(lambda _, s=sub: self._open(s))
            menu.addAction(act)
        menu.addSeparator()
        p = QAction('启动', self)
        p.triggered.connect(self.play)
        menu.addAction(p)
        d = QAction('删除', self)
        d.triggered.connect(self.remove)
        menu.addAction(d)
        menu.exec_(e.globalPos())

    def _open(self, sub):
        from ui.manage_dialogs import open_folder
        p = self.instance['gameDir'] if not sub else \
            os.path.join(self.instance['gameDir'], sub)
        os.makedirs(p, exist_ok=True)
        open_folder(p)

    # ---------------------------------------------------------- 拖拽导入
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        e.accept()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        files = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if not files:
            e.ignore()
            return
        from ui.instance_settings import DropImportDialog
        dlg = DropImportDialog(self.page, self.instance['gameDir'], files)
        dlg.exec_()
        e.acceptProposedAction()


class NewInstanceDialog(QDialog):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.setWindowTitle('新建实例')
        self.setMinimumSize(380, 220)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(self._label('实例名称'))
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName('LineEdit')
        self.name_edit.setPlaceholderText('例如：我的世界 1.20.1')
        layout.addWidget(self.name_edit)
        layout.addWidget(self._label('游戏版本（需已安装）'))
        self.version_combo = QComboBox()
        self.version_combo.setObjectName('ComboBox')
        root = page.app.data_root
        vdir = os.path.join(root, 'versions')
        installed = []
        if os.path.isdir(vdir):
            for d in sorted(os.listdir(vdir)):
                if is_installed(root, d):
                    installed.append(d)
        if installed:
            self.version_combo.addItems(installed)
        else:
            self.version_combo.addItem('（暂无已安装版本，请先到“版本”页安装）')
        layout.addWidget(self.version_combo)
        bar = QHBoxLayout()
        bar.addStretch(1)
        cancel = QPushButton('取消')
        cancel.setObjectName('GhostButton')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('创建')
        ok.setObjectName('PrimaryButton')
        ok.clicked.connect(self.accept_ok)
        bar.addWidget(cancel)
        bar.addWidget(ok)
        layout.addLayout(bar)

    def _label(self, text):
        l = QLabel(text)
        l.setObjectName('PageHint')
        return l

    def accept_ok(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, '提示', '请填写实例名称')
            return
        version = self.version_combo.currentText()
        create_instance(self.page.app.data_root, name, version, 'vanilla')
        self.page.refresh()
        self.accept()


class InstancesPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel('实例')
        title.setObjectName('PageTitle')
        head.addWidget(title)
        head.addStretch(1)
        self.new_btn = QPushButton('+ 新建实例')
        self.new_btn.setObjectName('PrimaryButton')
        self.new_btn.clicked.connect(self.new_instance)
        head.addWidget(self.new_btn)
        layout.addLayout(head)
        self.scroll = QScrollArea()
        self.scroll.setObjectName('Scroll')
        self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(12)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def new_instance(self):
        dlg = NewInstanceDialog(self)
        dlg.exec_()

    def open_settings(self, instance):
        from ui.instance_settings import InstanceSettingsDialog
        dlg = InstanceSettingsDialog(self, self.app, instance, on_saved=self.refresh)
        dlg.exec_()

    def refresh(self):
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        insts = list_instances(self.app.data_root)
        if not insts:
            empty = QLabel('还没有实例，点击右上角「新建实例」开始吧。')
            empty.setObjectName('PageHint')
            self.list_layout.addWidget(empty)
        else:
            for inst in insts:
                self.list_layout.addWidget(InstanceCard(inst, self))
        self.list_layout.addStretch(1)
