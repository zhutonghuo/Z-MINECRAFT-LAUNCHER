# -*- coding: utf-8 -*-
"""点「安装」时弹出的「选择要安装的加载器」对话框。

按目标 Minecraft 版本查询各加载器的可用性，让用户勾选需要的加载器并选版本。
游戏本体（原版基版本）始终会先安装，因为它是一切加载器的依赖。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QCheckBox, QFrame)

from core.loaders import LOADER_TYPES, list_loader_mc_versions, list_loader_versions
from ui.worker import Worker, Bridge

# 弹窗里展示的加载器顺序
_LOADER_ORDER = ['fabric', 'quilt', 'forge', 'neoforge', 'optifine']


class LoaderChoiceDialog(QDialog):
    def __init__(self, parent, mc_version, source, data_root=None):
        super().__init__(parent)
        self.mc_version = mc_version
        self.source = source
        self.data_root = data_root
        # code -> (checkbox, combo, supported)
        self._rows = {}
        self.selected = []
        # 用于把工作线程的结果安全地转回主线程再操作 UI
        self.bridge = Bridge()
        self.bridge.report.connect(self._on_bridge)
        self.setWindowTitle('选择要安装的加载器')
        self.setMinimumWidth(480)
        self._build_ui()
        self._load_availability()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        title = QLabel('为 Minecraft <b>%s</b> 选择要安装的加载器' % self.mc_version)
        title.setWordWrap(True)
        title.setObjectName('CardTitle')
        layout.addWidget(title)

        hint = QLabel('游戏本体将自动安装；勾选的加载器会各自生成一个实例。也可什么都不勾，只装原版。')
        hint.setObjectName('PageHint')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName('Sep')
        layout.addWidget(sep)

        self._status = QLabel('正在查询各加载器对 %s 的支持情况...' % self.mc_version)
        self._status.setObjectName('PageHint')
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        for code in _LOADER_ORDER:
            disp = dict(LOADER_TYPES).get(code, code)
            h = QHBoxLayout()
            cb = QCheckBox(disp)
            cb.setEnabled(False)
            cb.stateChanged.connect(self._on_any_toggled)
            combo = QComboBox()
            combo.setObjectName('ComboBox')
            combo.setMinimumWidth(220)
            combo.setEnabled(False)
            h.addWidget(cb)
            h.addStretch(1)
            h.addWidget(combo)
            layout.addLayout(h)
            self._rows[code] = (cb, combo, False)

        layout.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton('取消')
        cancel.setObjectName('ThemeButton')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('确定安装')
        ok.setObjectName('PrimaryButton')
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _on_any_toggled(self, _=None):
        # 勾选任意加载器时把状态文案收一下，避免误导
        if any(cb.isChecked() for cb, _, _ in self._rows.values()):
            self._status.setText('勾选完成点「确定安装」即可。')

    def _on_bridge(self, payload):
        """主线程槽：处理后台查询结果。payload = ('ok', out) 或 ('err', msg)"""
        kind = payload[0]
        if kind == 'err':
            self._status.setText('查询加载器失败（%s）。可直接点「确定安装」只装原版。'
                                 % payload[1])
            return
        out = payload[1]
        any_supported = False
        for code, (cb, combo, _) in self._rows.items():
            supported, vers = out.get(code, (False, []))
            if supported and vers:
                any_supported = True
                cb.setEnabled(True)
                combo.setEnabled(True)
                combo.blockSignals(True)
                combo.clear()
                for label, value in vers:
                    combo.addItem(label, value)
                combo.blockSignals(False)
                self._rows[code] = (cb, combo, True)
            else:
                cb.setEnabled(False)
                combo.setEnabled(False)
                cb.setText(cb.text() + '（该版本暂不提供）')
        if any_supported:
            self._status.setText('勾选需要的加载器即可（可不勾，只装原版）。')
        else:
            self._status.setText('当前没有查到可用的加载器版本，将只安装原版。')

    def _load_availability(self):
        """后台并发查询各加载器支持情况（走国内镜像 + 本地缓存，很快）"""
        from core.loaders import query_loader_support

        def job():
            return query_loader_support(
                self.data_root, list(_LOADER_ORDER), self.mc_version, self.source)

        def on_done(out):
            self.bridge.report.emit(('ok', out))

        def on_error(e):
            self.bridge.report.emit(('err', str(e)))

        w = Worker(job)
        # 必须持有引用：QThread 运行中被 GC 回收会让 Qt 直接 abort（无报错闪退）
        self._worker = w
        w.done.connect(on_done)
        w.error.connect(on_error)
        w.finished.connect(w.deleteLater)
        w.start()

    def get_choices(self):
        loaders = []
        for code, (cb, combo, supported) in self._rows.items():
            if supported and cb.isChecked() and combo.count() > 0:
                loaders.append((code, combo.currentData()))
        return loaders
