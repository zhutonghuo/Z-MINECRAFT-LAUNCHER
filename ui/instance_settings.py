# -*- coding: utf-8 -*-
"""实例「设置」对话框与拖拽导入对话框。

- InstanceSettingsDialog：右键实例卡片打开的「新页面设置」。可改实例名、Java/游戏
  参数、分辨率；一键打开各类文件夹；一键进入 Mod / 资源包 / 光影 / 世界 的管理。
- DropImportDialog：把文件拖到实例卡片后，让用户选择每个文件放进哪个文件夹
  （Mod / 资源包 / 光影 / 世界 / 实例根目录），再复制进去。
"""
import os
import shutil

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QLineEdit, QSpinBox, QScrollArea, QMessageBox,
                             QComboBox, QFileDialog, QFormLayout, QWidget, QLayout)

from core.instances import instances_dir, save_instance
from ui.manage_dialogs import open_folder, FolderManageDialog, WorldManageDialog


class InstanceSettingsDialog(QDialog):
    def __init__(self, parent, app, instance, on_saved=None):
        super().__init__(parent)
        self.app = app
        self.instance = instance
        self.on_saved = on_saved
        self.data_root = app.data_root
        self.game_dir = instance['gameDir']
        self.setWindowTitle('实例设置 · ' + instance['name'])
        self.setMinimumSize(560, 560)
        self.setObjectName('Page')

        scroll = QScrollArea(self)
        scroll.setObjectName('Scroll')
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel('实例设置')
        title.setObjectName('PageTitle')
        layout.addWidget(title)

        # ---- 基本信息（只读）
        info = QLabel('版本：%s    加载器：%s' % (
            instance.get('versionId', '-'),
            instance.get('modLoader', 'vanilla')))
        info.setObjectName('PageHint')
        layout.addWidget(info)

        # ---- 可编辑：名称
        self.name_edit = QLineEdit(instance['name'])
        self.name_edit.setObjectName('LineEdit')
        layout.addLayout(self._row('实例名称', self.name_edit))

        # ---- 可编辑：Java / 游戏 参数
        self.java_args = QLineEdit(instance.get('javaArgs', ''))
        self.java_args.setObjectName('LineEdit')
        self.java_args.setPlaceholderText('额外 JVM 参数，如 -XX:+UseG1GC')
        layout.addLayout(self._row('Java 参数', self.java_args))

        self.game_args = QLineEdit(instance.get('gameArgs', ''))
        self.game_args.setObjectName('LineEdit')
        self.game_args.setPlaceholderText('额外游戏参数（一般不需要）')
        layout.addLayout(self._row('游戏参数', self.game_args))

        # ---- 分辨率
        res = instance.get('resolution') or {}
        self.res_w = QSpinBox(); self.res_w.setRange(0, 7680); self.res_w.setValue(int(res.get('width', 0) or 0))
        self.res_h = QSpinBox(); self.res_h.setRange(0, 4320); self.res_h.setValue(int(res.get('height', 0) or 0))
        self.res_w.setObjectName('Spin'); self.res_h.setObjectName('Spin')
        res_row = QHBoxLayout()
        res_row.addWidget(self.res_w); res_row.addWidget(QLabel('×')); res_row.addWidget(self.res_h)
        res_row.addWidget(QLabel('（都填 0 表示使用窗口默认大小）'))
        layout.addLayout(self._row('分辨率', res_row))

        # ---- 一键打开各类文件夹
        layout.addSpacing(6)
        open_title = QLabel('打开文件夹')
        open_title.setObjectName('SettingLabel')
        layout.addWidget(open_title)
        folders = [
            ('打开版本文件夹', ''),
            ('打开 Mod 文件夹', 'mods'),
            ('打开资源包文件夹', 'resourcepacks'),
            ('打开光影文件夹', 'shaderpacks'),
            ('打开世界文件夹', 'saves'),
        ]
        frow = QHBoxLayout()
        for label, sub in folders:
            b = QPushButton(label)
            b.setObjectName('ThemeButton')
            b.clicked.connect(lambda _, s=sub: self._open(s))
            frow.addWidget(b)
        frow.addStretch(1)
        layout.addLayout(frow)

        # ---- 管理
        layout.addSpacing(6)
        mg_title = QLabel('管理内容')
        mg_title.setObjectName('SettingLabel')
        layout.addWidget(mg_title)
        mrow = QHBoxLayout()
        for label, fn in [
            ('管理 Mod', lambda: self._manage_folder('mods', '管理 Mod')),
            ('管理资源包', lambda: self._manage_folder('resourcepacks', '管理资源包')),
            ('管理光影', lambda: self._manage_folder('shaderpacks', '管理光影')),
            ('管理世界', self._manage_worlds),
        ]:
            b = QPushButton(label)
            b.setObjectName('PrimaryButton' if '世界' in label else 'ThemeButton')
            b.clicked.connect(fn)
            mrow.addWidget(b)
        mrow.addStretch(1)
        layout.addLayout(mrow)

        layout.addSpacing(14)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton('取消')
        cancel.setObjectName('GhostButton')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('保存')
        ok.setObjectName('PrimaryButton')
        ok.clicked.connect(self.save)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

    def _row(self, label, widget_or_layout):
        h = QHBoxLayout()
        l = QLabel(label)
        l.setObjectName('SettingLabel')
        l.setFixedWidth(96)
        h.addWidget(l)
        if isinstance(widget_or_layout, QLayout):
            h.addLayout(widget_or_layout, 1)
        else:
            h.addWidget(widget_or_layout, 1)
        return h

    def _open(self, sub):
        p = self.game_dir if not sub else os.path.join(self.game_dir, sub)
        os.makedirs(p, exist_ok=True)
        open_folder(p)

    def _manage_folder(self, folder_name, title):
        dlg = FolderManageDialog(self, self.game_dir, folder_name, title, self.instance)
        dlg.exec_()

    def _manage_worlds(self):
        dlg = WorldManageDialog(self, self.game_dir)
        dlg.exec_()

    def save(self):
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, '提示', '实例名称不能为空')
            return
        inst = dict(self.instance)
        old_name = inst['name']
        inst['javaArgs'] = self.java_args.text().strip()
        inst['gameArgs'] = self.game_args.text().strip()
        w = self.res_w.value(); h = self.res_h.value()
        inst['resolution'] = {'width': w, 'height': h} if (w and h) else None

        if new_name != old_name:
            base = instances_dir(self.data_root)
            old_dir = os.path.join(base, old_name)
            new_dir = os.path.join(base, new_name)
            if os.path.exists(new_dir):
                QMessageBox.warning(self, '提示',
                                    '已存在同名实例「%s」，请换一个名称。' % new_name)
                return
            try:
                os.makedirs(base, exist_ok=True)
                shutil.move(old_dir, new_dir)
            except Exception as e:
                QMessageBox.warning(self, '重命名失败',
                                    '无法重命名实例文件夹：%s' % e)
                return
            inst['name'] = new_name
            inst['gameDir'] = os.path.join(new_dir, '.minecraft')
            inst['_dir'] = new_dir

        save_instance(self.data_root, inst)
        self.instance.update(inst)
        if self.on_saved:
            self.on_saved()
        self.accept()


class DropImportDialog(QDialog):
    """把拖入的文件分发到实例的对应文件夹。"""

    TARGETS = [
        ('Mod', 'mods'),
        ('资源包', 'resourcepacks'),
        ('光影', 'shaderpacks'),
        ('世界', 'saves'),
        ('实例根目录', ''),
    ]

    def __init__(self, parent, game_dir, files):
        super().__init__(parent)
        self.game_dir = game_dir
        self.files = files
        self.setWindowTitle('导入到实例')
        self.setMinimumSize(560, 420)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        t = QLabel('把这些文件放进实例的哪个文件夹？')
        t.setObjectName('PageTitle')
        layout.addWidget(t)
        hint = QLabel('说明：.jar 默认进 Mod；.zip 默认按文件名猜测（含 shader→光影、'
                      'resource→资源包）；文件夹 / .mcworld 默认进世界。')
        hint.setObjectName('Hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setObjectName('Scroll')
        self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(6)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)

        self.combos = []
        for f in files:
            row = QHBoxLayout()
            name = QLabel(os.path.basename(f))
            name.setObjectName('CardTitle')
            name.setFixedWidth(280)
            cb = QComboBox()
            cb.setObjectName('ComboBox')
            for label, _ in self.TARGETS:
                cb.addItem(label)
            cb.setCurrentIndex(self._guess(f))
            self.combos.append(cb)
            row.addWidget(name)
            row.addWidget(QLabel('→'))
            row.addWidget(cb, 1)
            self.list_layout.addLayout(row)
        self.list_layout.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton('取消')
        cancel.setObjectName('GhostButton')
        cancel.clicked.connect(self.reject)
        ok = QPushButton('导入')
        ok.setObjectName('PrimaryButton')
        ok.clicked.connect(self.do_import)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)

    def _guess(self, f):
        name = os.path.basename(f).lower()
        if os.path.isdir(f) or name.endswith('.mcworld'):
            return 3  # 世界
        if name.endswith('.jar'):
            return 0  # Mod
        if 'shader' in name:
            return 2
        if 'resource' in name or 'rp' in name:
            return 1
        return 0

    def do_import(self):
        copied = 0
        errors = []
        for f, cb in zip(self.files, self.combos):
            sub = self.TARGETS[cb.currentIndex()][1]
            try:
                if sub == 'saves':
                    self._import_world(f)
                else:
                    dest_dir = self.game_dir if not sub else os.path.join(self.game_dir, sub)
                    os.makedirs(dest_dir, exist_ok=True)
                    base = os.path.basename(f)
                    dest = os.path.join(dest_dir, base)
                    if os.path.isdir(f):
                        if os.path.exists(dest):
                            dest += '_' + str(int(__import__('time').time()))
                        shutil.copytree(f, dest)
                    else:
                        shutil.copy2(f, dest)
                copied += 1
            except Exception as e:
                errors.append('%s：%s' % (os.path.basename(f), e))
        msg = '成功导入 %d 个文件。' % copied
        if errors:
            msg += '\n失败：\n' + '\n'.join(errors)
        QMessageBox.information(self, '导入完成', msg)
        self.accept()

    def _import_world(self, f):
        saves = os.path.join(self.game_dir, 'saves')
        os.makedirs(saves, exist_ok=True)
        name = os.path.basename(f)
        if name.endswith('.mcworld'):
            import zipfile
            target = os.path.join(saves, name[:-len('.mcworld')])
            i = 0
            while os.path.exists(target):
                i += 1
                target = os.path.join(saves, name[:-len('.mcworld')] + ('_%d' % i))
            os.makedirs(target, exist_ok=True)
            with zipfile.ZipFile(f, 'r') as z:
                z.extractall(target)
        elif os.path.isdir(f):
            target = os.path.join(saves, name)
            i = 0
            while os.path.exists(target):
                i += 1
                target = os.path.join(saves, name + ('_%d' % i))
            shutil.copytree(f, target)
        else:
            raise Exception('世界需要是文件夹或 .mcworld 压缩包')
