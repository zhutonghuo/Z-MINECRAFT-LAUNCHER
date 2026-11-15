# -*- coding: utf-8 -*-
"""实例内各类内容的「管理」对话框。

- FolderManageDialog：通用文件夹管理（Mod / 资源包 / 光影），支持
  启用/禁用（.disabled 切换）、删除、打开所在文件夹。
  光影页额外提供「一键安装 Iris（光影加载器）」。
- WorldManageDialog：世界管理，展示封面（icon.png）、名称（读 level.dat）、
  改名（同时改文件夹名与 level.dat 的 LevelName）、删除。
"""
import os
import shutil
import zipfile

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QFrame, QScrollArea, QMessageBox, QComboBox, QWidget,
                             QInputDialog, QFileDialog, QApplication, QSizePolicy)

from ui.widgets import fmt_size
from ui.worker import Worker, Bridge
from core.download import Progress, download_all
from core.modrinth import resolve_download, target_path


class EntryFrame(QFrame):
    def __init__(self, parent_dialog, path, is_dir=False, checked=True):
        super().__init__()
        self.pd = parent_dialog
        self.path = path
        self.is_dir = is_dir
        self.checked = checked
        self.setObjectName('Card')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        name = QLabel(os.path.basename(path))
        name.setObjectName('CardTitle')
        layout.addWidget(name, 1)

        if not is_dir:
            size = QLabel(fmt_size(os.path.getsize(path)) if os.path.exists(path) else '')
            size.setObjectName('CardSub')
            layout.addWidget(size)

        if not is_dir and path.endswith('.disabled'):
            self.checked = False

        if not is_dir:
            self.toggle_btn = QPushButton('启用' if not self.checked else '禁用')
            self.toggle_btn.setObjectName('GhostButton')
            self.toggle_btn.setFixedWidth(64)
            self.toggle_btn.clicked.connect(self.toggle)
            layout.addWidget(self.toggle_btn)

        self.del_btn = QPushButton('删除')
        self.del_btn.setObjectName('GhostButton')
        self.del_btn.setFixedWidth(64)
        self.del_btn.clicked.connect(self.remove)
        layout.addWidget(self.del_btn)

    def refresh_checked(self):
        disabled = self.path.endswith('.disabled')
        if hasattr(self, 'toggle_btn'):
            self.toggle_btn.setText('启用' if disabled else '禁用')

    def toggle(self):
        base = self.path
        try:
            if base.endswith('.disabled'):
                new = base[:-len('.disabled')]
                os.rename(base, new)
                self.path = new
            else:
                new = base + '.disabled'
                os.rename(base, new)
                self.path = new
            self.refresh_checked()
            self.pd.mark_changed()
        except Exception as e:
            QMessageBox.warning(self.pd, '操作失败', '无法切换启用状态：%s' % e)

    def remove(self):
        name = os.path.basename(self.path)
        r = QMessageBox.question(self.pd, '删除确认',
                                 '确定删除「%s」？此操作不可恢复。' % name,
                                 QMessageBox.Yes | QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        try:
            if self.is_dir:
                shutil.rmtree(self.path)
            else:
                os.remove(self.path)
            self.deleteLater()
            self.pd.mark_changed()
        except Exception as e:
            QMessageBox.warning(self.pd, '删除失败', '无法删除：%s' % e)


class FolderManageDialog(QDialog):
    def __init__(self, parent, game_dir, folder_name, title, instance=None):
        super().__init__(parent)
        self.game_dir = game_dir
        self.folder_name = folder_name
        self.instance = instance
        self.changed = False
        self.setWindowTitle(title)
        self.setMinimumSize(620, 460)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setObjectName('PageTitle')
        head.addWidget(t)
        head.addStretch(1)
        add_btn = QPushButton('添加文件')
        add_btn.setObjectName('PrimaryButton')
        add_btn.clicked.connect(self.add_files)
        head.addWidget(add_btn)
        open_btn = QPushButton('打开文件夹')
        open_btn.setObjectName('ThemeButton')
        open_btn.clicked.connect(self.open_folder)
        head.addWidget(open_btn)
        layout.addLayout(head)

        hint = QLabel('启用 / 禁用：通过给文件名加 .disabled 后缀实现（游戏不会加载被禁用的文件）。')
        hint.setObjectName('Hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        if folder_name == 'shaderpacks' and instance and instance.get('modLoader') == 'fabric':
            iris_btn = QPushButton('安装 Iris + Sodium（光影加载器，需 Fabric）')
            iris_btn.setObjectName('PrimaryButton')
            iris_btn.clicked.connect(self.install_iris)
            layout.addWidget(iris_btn)

        self.scroll = QScrollArea()
        self.scroll.setObjectName('Scroll')
        self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(8)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def folder_path(self):
        return os.path.join(self.game_dir, self.folder_name)

    def open_folder(self):
        p = self.folder_path()
        os.makedirs(p, exist_ok=True)
        open_folder(p)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择文件', '',
            'Mod/资源包/光影 (*.jar *.zip);;所有文件 (*)')
        if not paths:
            return
        dest = self.folder_path()
        os.makedirs(dest, exist_ok=True)
        added = []
        for src in paths:
            name = os.path.basename(src)
            target = os.path.join(dest, name)
            if os.path.exists(target):
                base, ext = os.path.splitext(name)
                i = 1
                while os.path.exists(os.path.join(dest, base + ' (%d)' % i + ext)):
                    i += 1
                target = os.path.join(dest, base + ' (%d)' % i + ext)
            try:
                shutil.copy2(src, target)
                added.append(os.path.basename(target))
            except Exception as e:
                QMessageBox.warning(self, '导入失败', '无法复制 %s：%s' % (name, e))
        if added:
            self.refresh()
            self.mark_changed()
            QMessageBox.information(self, '导入完成',
                                    '已添加 %d 个文件到 %s。' % (len(added), self.folder_name))

    def refresh(self):
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        p = self.folder_path()
        os.makedirs(p, exist_ok=True)
        entries = []
        for name in sorted(os.listdir(p)):
            full = os.path.join(p, name)
            if os.path.isdir(full):
                entries.append((full, True))
            elif os.path.isfile(full):
                entries.append((full, False))
        if not entries:
            empty = QLabel('这个文件夹还是空的。点上方「添加文件」选择本地文件或 .zip 包，或把文件拖到左侧实例卡片。')
            empty.setObjectName('PageHint')
            self.list_layout.addWidget(empty)
        else:
            for full, is_dir in entries:
                self.list_layout.addWidget(EntryFrame(self, full, is_dir))
        self.list_layout.addStretch(1)

    def mark_changed(self):
        self.changed = True

    def install_iris(self):
        mc = self.instance['versionId']
        from core.modrinth import search_projects
        dlg = _IrisProgress(self, self.game_dir, mc)
        dlg.exec_()
        self.refresh()
        self.mark_changed()


class _IrisProgress(QDialog):
    """后台下载 Iris + Sodium 的小进度框。"""
    def __init__(self, parent, game_dir, mc_version):
        super().__init__(parent)
        self.game_dir = game_dir
        self.mc_version = mc_version
        self.setWindowTitle('安装光影加载器')
        self.setMinimumWidth(420)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        self.label = QLabel('正在从 Modrinth 解析 Iris / Sodium...')
        self.label.setObjectName('PageHint')
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.bridge = Bridge()
        self.bridge.report.connect(self.on_report)
        self.prog = Progress(0, '准备')
        self.ok = False
        self._start()

    def _start(self):
        from core.modrinth import resolve_download, target_path
        from core.download import download_all, Progress

        def job():
            results = []
            for slug in ('iris', 'sodium'):
                info = resolve_download(slug, 'mod', self.mc_version)
                dest = target_path(self.game_dir, 'mod', info['filename'])
                task = {'url': info['url'], 'dest': dest, 'sha1': info['sha1'],
                        'size': info['size']}
                prog = Progress(info['size'], '下载 ' + info['filename'])
                download_all([task], concurrency=8, segmented=True,
                             progress_cb=self.bridge.report.emit, prog=prog,
                             stage='下载 ' + info['filename'])
                results.append(info['filename'])
            return results

        w = Worker(job)
        self._w = w
        w.done.connect(self.on_done)
        w.error.connect(self.on_error)
        w.finished.connect(w.deleteLater)
        w.start()

    def on_report(self, info):
        if isinstance(info, dict):
            stage = info.get('stage', '')
            done = info.get('done', 0)
            total = info.get('total', 0)
            if total > 0:
                self.label.setText('%s：%d%%' % (stage, min(100, int(done * 100 / total))))
            else:
                self.label.setText('%s：%s' % (stage, fmt_size(done)))

    def on_done(self, res):
        self.ok = True
        self.label.setText('已安装到 Mod 文件夹：' + '、'.join(res))
        # 完成提醒：播放提示音 + 发系统通知
        try:
            from core.notify import notify_complete
            app = getattr(self, 'app', None)
            if app is None:
                p = self.parent()
                app = getattr(p, 'app', None)
            settings = getattr(app, 'settings', None) if app else None
            notify_complete('ZMCLauncher', '光影加载器安装完成', settings, app)
        except Exception:
            pass
        QMessageBox.information(self, '完成', '光影加载器已安装到实例的 Mod 文件夹。\n'
                                '进入游戏后到「视频设置 → 光影」里开启即可。')
        self.accept()

    def on_error(self, e):
        self.label.setText('安装失败：' + str(e))
        QMessageBox.warning(self, '安装失败', str(e))
        self.reject()


class WorldEntry(QFrame):
    def __init__(self, parent_dialog, world_dir):
        super().__init__()
        self.pd = parent_dialog
        self.world_dir = world_dir
        self.setObjectName('Card')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.cover = QLabel()
        self.cover.setFixedSize(64, 64)
        self.cover.setAlignment(Qt.AlignCenter)
        icon = os.path.join(world_dir, 'icon.png')
        pm = QPixmap(icon) if os.path.isfile(icon) else QPixmap()
        if not pm.isNull():
            self.cover.setPixmap(pm.scaled(64, 64, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        else:
            self.cover.setText('🌍')
            self.cover.setStyleSheet('font-size:30px;background:#1b1d23;'
                                     'border-radius:8px;')
        layout.addWidget(self.cover)

        info = QVBoxLayout()
        info.setSpacing(3)
        self.folder_name = os.path.basename(world_dir)
        self.name = _world_name(world_dir) or self.folder_name
        title = QLabel(self.name)
        title.setObjectName('CardTitle')
        sub = QLabel('文件夹：' + self.folder_name)
        sub.setObjectName('CardSub')
        info.addWidget(title)
        info.addWidget(sub)
        layout.addLayout(info, 1)

        rename_btn = QPushButton('改名')
        rename_btn.setObjectName('GhostButton')
        rename_btn.setFixedWidth(64)
        rename_btn.clicked.connect(self.rename_world)
        del_btn = QPushButton('删除')
        del_btn.setObjectName('GhostButton')
        del_btn.setFixedWidth(64)
        del_btn.clicked.connect(self.remove)
        layout.addWidget(rename_btn)
        layout.addWidget(del_btn)

    def rename_world(self):
        new = QInputDialog.getText(self.pd, '重命名世界',
                                  '请输入新的世界名称：', text=self.name)
        if not new[1]:
            return
        new_name = new[0].strip()
        if not new_name:
            return
        if new_name == self.name:
            return
        try:
            from core import nbt
            level = os.path.join(self.world_dir, 'level.dat')
            if os.path.isfile(level):
                nbt.set_level_name(level, new_name)
            # 同步把文件夹也改名（游戏以文件夹定位存档）
            parent = os.path.dirname(self.world_dir)
            new_dir = os.path.join(parent, new_name)
            if new_dir != self.world_dir and not os.path.exists(new_dir):
                os.rename(self.world_dir, new_dir)
                self.world_dir = new_dir
            self.name = new_name
            self.pd.refresh()
            self.pd.mark_changed()
        except Exception as e:
            QMessageBox.warning(self.pd, '改名失败', '无法重命名世界：%s' % e)

    def remove(self):
        r = QMessageBox.question(self.pd, '删除世界',
                                 '确定删除世界「%s」？此操作不可恢复。' % self.name,
                                 QMessageBox.Yes | QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(self.world_dir)
            self.deleteLater()
            self.pd.mark_changed()
        except Exception as e:
            QMessageBox.warning(self.pd, '删除失败', '无法删除世界：%s' % e)


def _world_name(world_dir):
    from core import nbt
    return nbt.get_level_name(os.path.join(world_dir, 'level.dat'))


def extract_world(zip_path, dest):
    with zipfile.ZipFile(zip_path, 'r') as z:
        names = z.namelist()
        tops = set()
        for n in names:
            if not n:
                continue
            tops.add(n.split('/')[0])
        if len(tops) == 1:
            root = list(tops)[0]
            if all(n == root or n.startswith(root + '/') for n in names if n):
                os.makedirs(dest, exist_ok=True)
                for n in names:
                    if n.endswith('/') or n == root:
                        continue
                    rel = n[len(root) + 1:]
                    if not rel:
                        continue
                    out = os.path.join(dest, rel)
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    with z.open(n) as f, open(out, 'wb') as o:
                        o.write(f.read())
                return
        os.makedirs(dest, exist_ok=True)
        z.extractall(dest)


class WorldManageDialog(QDialog):
    def __init__(self, parent, game_dir):
        super().__init__(parent)
        self.game_dir = game_dir
        self.changed = False
        self.setWindowTitle('管理世界')
        self.setMinimumSize(640, 480)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel('管理世界')
        t.setObjectName('PageTitle')
        head.addWidget(t)
        head.addStretch(1)
        addfile_btn = QPushButton('添加世界(文件)')
        addfile_btn.setObjectName('PrimaryButton')
        addfile_btn.clicked.connect(self.add_world_file)
        head.addWidget(addfile_btn)
        adddir_btn = QPushButton('添加世界(文件夹)')
        adddir_btn.setObjectName('PrimaryButton')
        adddir_btn.clicked.connect(self.add_world_folder)
        head.addWidget(adddir_btn)
        open_btn = QPushButton('打开存档文件夹')
        open_btn.setObjectName('ThemeButton')
        open_btn.clicked.connect(self.open_folder)
        head.addWidget(open_btn)
        layout.addLayout(head)

        hint = QLabel('封面来自每个世界的 icon.png；名称读取自 level.dat（改名会同时更新文件夹与存档内名称）。')
        hint.setObjectName('Hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setObjectName('Scroll')
        self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(8)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)
        self.refresh()

    def open_folder(self):
        p = os.path.join(self.game_dir, 'saves')
        os.makedirs(p, exist_ok=True)
        open_folder(p)

    def add_world_file(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, '选择世界文件', '', '世界文件 (*.mcworld *.zip);;所有文件 (*)')
        if not paths:
            return
        saves = os.path.join(self.game_dir, 'saves')
        os.makedirs(saves, exist_ok=True)
        added = []
        for src in paths:
            name = os.path.basename(src)
            base = os.path.splitext(name)[0]
            dest = os.path.join(saves, base)
            if os.path.exists(dest):
                i = 1
                while os.path.exists(dest + ' (%d)' % i):
                    i += 1
                dest = dest + ' (%d)' % i
            try:
                extract_world(src, dest)
                added.append(os.path.basename(dest))
            except Exception as e:
                QMessageBox.warning(self, '导入失败', '无法导入 %s：%s' % (name, e))
        if added:
            self.refresh()
            self.mark_changed()
            QMessageBox.information(self, '导入完成', '已导入 %d 个世界。' % len(added))

    def add_world_folder(self):
        src = QFileDialog.getExistingDirectory(self, '选择世界文件夹', '')
        if not src:
            return
        saves = os.path.join(self.game_dir, 'saves')
        os.makedirs(saves, exist_ok=True)
        name = os.path.basename(src.rstrip('/\\'))
        dest = os.path.join(saves, name)
        if os.path.exists(dest):
            i = 1
            while os.path.exists(dest + ' (%d)' % i):
                i += 1
            dest = dest + ' (%d)' % i
        try:
            shutil.copytree(src, dest)
            self.refresh()
            self.mark_changed()
            QMessageBox.information(self, '导入完成', '已导入世界：%s' % os.path.basename(dest))
        except Exception as e:
            QMessageBox.warning(self, '导入失败', '无法复制文件夹：%s' % e)

    def _extract_world(self, zip_path, dest):
        with zipfile.ZipFile(zip_path, 'r') as z:
            names = z.namelist()
            tops = set()
            for n in names:
                if not n:
                    continue
                tops.add(n.split('/')[0])
            if len(tops) == 1:
                root = list(tops)[0]
                if all(n == root or n.startswith(root + '/') for n in names if n):
                    os.makedirs(dest, exist_ok=True)
                    for n in names:
                        if n.endswith('/') or n == root:
                            continue
                        rel = n[len(root) + 1:]
                        if not rel:
                            continue
                        out = os.path.join(dest, rel)
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        with z.open(n) as f, open(out, 'wb') as o:
                            o.write(f.read())
                    return
            os.makedirs(dest, exist_ok=True)
            z.extractall(dest)

    def refresh(self):
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        p = os.path.join(self.game_dir, 'saves')
        if not os.path.isdir(p):
            empty = QLabel('还没有世界。进入游戏创建一个世界后，会出现在这里。')
            empty.setObjectName('PageHint')
            self.list_layout.addWidget(empty)
        else:
            worlds = [d for d in sorted(os.listdir(p))
                      if os.path.isdir(os.path.join(p, d))]
            if not worlds:
                empty = QLabel('还没有世界。进入游戏创建一个世界后，会出现在这里。')
                empty.setObjectName('PageHint')
                self.list_layout.addWidget(empty)
            else:
                for d in worlds:
                    self.list_layout.addWidget(WorldEntry(self, os.path.join(p, d)))
        self.list_layout.addStretch(1)

    def mark_changed(self):
        self.changed = True


def open_folder(path):
    try:
        os.startfile(path)
    except Exception:
        try:
            import subprocess
            subprocess.run(['explorer', path], shell=True)
        except Exception:
            pass
