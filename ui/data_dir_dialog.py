import os

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QSpacerItem, QSizePolicy,
                             QFileDialog)
from PyQt5.QtCore import Qt

DEFAULT_SUGGEST = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')), '.mclauncherpy')


class DataDirDialog(QDialog):
    """首次启动 / 数据目录丢失时弹出，让用户选择数据（账号 + 游戏）存放位置。

    选择结果保存在 self.chosen_path；调用方负责把它记到记忆文件并作为 dataRoot。
    取消按钮也会回退到默认位置，避免流程卡死。
    """

    def __init__(self, parent=None, suggest=None, lost=False):
        super().__init__(parent)
        self.chosen_path = suggest or DEFAULT_SUGGEST
        self.setWindowTitle('选择数据存放位置')
        self.setMinimumWidth(580)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build(lost)

    def _build(self, lost):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)

        title = QLabel('选择数据存放位置')
        title.setObjectName('PageTitle')
        root.addWidget(title)

        if lost:
            warn = QLabel('⚠ 上次选择的数据目录已不存在（可能 U 盘被拔出、文件夹被移动或删除）。\n'
                          '请重新选择数据存放位置。')
            warn.setObjectName('Hint')
            warn.setStyleSheet('color:#e8a33d;')
            root.addWidget(warn)

        hint = QLabel(
            '这个文件夹将用来保存：\n'
            '① 你的账号登录信息（正版 / 离线 / 第三方 Yggdrasil 服务器）\n'
            '② 已下载的游戏版本、Java 库、资源文件、日志\n\n'
            '建议放在稳定的位置（如 D 盘）；不要放进会被拔出或移动的 U 盘，\n'
            '除非你专门想做“便携版”（整个文件夹带着走）。\n'
            '选择后会被记住；之后每次启动都会检查该位置是否还在，若已丢失会重新让你选择。'
        )
        hint.setObjectName('PageHint')
        hint.setWordWrap(True)
        root.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.edit = QLineEdit(self.chosen_path)
        self.edit.setObjectName('LineEdit')
        browse = QPushButton('浏览...')
        browse.setObjectName('GhostButton')
        browse.clicked.connect(self._browse)
        row.addWidget(self.edit, 1)
        row.addWidget(browse)
        root.addLayout(row)

        self.status = QLabel('')
        self.status.setObjectName('Hint')
        root.addWidget(self.status)

        root.addSpacerItem(QSpacerItem(0, 10, QSizePolicy.Minimum,
                                      QSizePolicy.Expanding))

        btns = QHBoxLayout()
        btns.setSpacing(10)
        default_btn = QPushButton('使用默认位置')
        default_btn.setObjectName('GhostButton')
        default_btn.clicked.connect(self._use_default)
        cancel_btn = QPushButton('取消')
        cancel_btn.setObjectName('GhostButton')
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton('确认使用此位置')
        ok_btn.setObjectName('PrimaryButton')
        ok_btn.clicked.connect(self._accept)
        btns.addStretch(1)
        btns.addWidget(default_btn)
        btns.addWidget(cancel_btn)
        btns.addWidget(ok_btn)
        root.addLayout(btns)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, '选择数据文件夹', self.edit.text() or os.path.expanduser('~'))
        if d:
            self.edit.setText(d)
            self.status.setText('')

    def _use_default(self):
        self.edit.setText(DEFAULT_SUGGEST)
        self.chosen_path = DEFAULT_SUGGEST
        self.accept()

    def _accept(self):
        p = self.edit.text().strip()
        if not p:
            p = DEFAULT_SUGGEST
        try:
            os.makedirs(p, exist_ok=True)
            test = os.path.join(p, '.write_test')
            with open(test, 'w', encoding='utf-8') as f:
                f.write('ok')
            os.remove(test)
        except Exception as e:
            self.status.setText('该位置无法写入：%s\n请换一个可写的位置。' % e)
            return
        self.chosen_path = p
        self.accept()
