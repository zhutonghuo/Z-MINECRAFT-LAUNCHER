# -*- coding: utf-8 -*-
import os

from PyQt5.QtCore import Qt, QTimer, QPoint
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QLineEdit, QComboBox, QMessageBox,
                             QDialog)

from core.manifest import get_manifest
from core.installer import install_vanilla, is_installed
from core.instances import create_instance
from core.loaders import (LOADER_TYPES, install_loader, suggest_instance_name)
from ui.widgets import ProgressPanel, fmt_size
from ui.worker import Worker, Bridge
from ui.loader_choice_dialog import LoaderChoiceDialog


class VersionRow(QFrame):
    def __init__(self, version, page):
        super().__init__()
        self.version = version
        self.page = page
        self.setObjectName('Card')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        info = QVBoxLayout()
        info.setSpacing(3)
        name = QLabel(version['id'])
        name.setObjectName('CardTitle')
        typ = QLabel({'release': '正式版', 'snapshot': '快照', 'old_beta': '旧版 Beta',
                      'old_alpha': '旧版 Alpha'}.get(version.get('type'), version.get('type', '')))
        typ.setObjectName('CardSub')
        info.addWidget(name)
        info.addWidget(typ)
        layout.addLayout(info, 1)
        self.btn = QPushButton()
        self.btn.setObjectName('InstallButton')
        self._update_state()
        self.btn.clicked.connect(self.install)
        layout.addWidget(self.btn)

    def _update_state(self):
        if is_installed(self.page.app.data_root, self.version['id']):
            self.btn.setText('已安装')
            self.btn.setEnabled(False)
        else:
            self.btn.setText('安装')
            self.btn.setEnabled(True)

    def install(self):
        self.page.start_install(self)


class VersionPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName('Page')
        self.manifest = None
        self.versions = []
        self._rows = []
        self._active_row = None
        self._install_vid = ''
        self._java_path = None
        self.bridge = Bridge()
        self.bridge.report.connect(self.on_report)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        head = QHBoxLayout()
        title = QLabel('版本')
        title.setObjectName('PageTitle')
        head.addWidget(title)
        head.addStretch(1)
        layout.addLayout(head)

        # 原版检索区
        find = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setObjectName('LineEdit')
        self.search.setPlaceholderText('搜索版本号...')
        self.search.textChanged.connect(self._schedule_rebuild)
        self.cat = QComboBox()
        self.cat.setObjectName('ComboBox')
        self.cat.addItems(['全部', '正式版', '快照', '旧版'])
        self.cat.currentTextChanged.connect(self._schedule_rebuild)
        self.refresh_btn = QPushButton('刷新清单')
        self.refresh_btn.setObjectName('ThemeButton')
        self.refresh_btn.clicked.connect(self.load)
        find.addWidget(self.search)
        find.addWidget(self.cat)
        find.addWidget(self.refresh_btn)
        layout.addLayout(find)

        self.prog = ProgressPanel()
        layout.addWidget(self.prog)

        self.status_lbl = QLabel('正在加载版本清单...')
        self.status_lbl.setObjectName('PageHint')
        layout.addWidget(self.status_lbl)
        self.scroll = QScrollArea()
        self.scroll.setObjectName('Scroll')
        self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setSpacing(10)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)
        self.load()

    # ---------------------------------------------------------- 清单加载
    def _schedule_rebuild(self):
        if not hasattr(self, '_debounce'):
            self._debounce = QTimer(self)
            self._debounce.setSingleShot(True)
            self._debounce.setInterval(250)
            self._debounce.timeout.connect(self.rebuild)
        self._debounce.start()

    def load(self):
        self.status_lbl.setText('正在加载版本清单...')
        source = self.app.settings['downloadSource']

        def job():
            return get_manifest(source)

        w = Worker(job)
        w.done.connect(self.on_loaded)
        w.error.connect(self.on_manifest_error)
        w.finished.connect(w.deleteLater)
        self._load_worker = w
        w.start()

    def on_loaded(self, manifest):
        self.manifest = manifest
        self.versions = manifest.get('versions', [])
        self.status_lbl.setText('共 %d 个版本' % len(self.versions))
        self.rebuild()

    def on_manifest_error(self, e):
        from core.http import friendly_error
        reason = friendly_error(e)
        msg = '清单加载失败：%s\n\n已依次尝试 BMCLAPI、MCBBS、官方源仍失败。' \
              '常见原因与对策：\n' \
              '· 网络不通或被防火墙拦截 → 检查网络；\n' \
              '· 系统/自定义代理异常 → 到「设置」把代理改为「禁用」后重试；\n' \
              '· 镜像全部抽风 → 稍后再试或换网络。' % reason
        self.status_lbl.setText('清单加载失败：' + reason)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle('清单加载失败')
        box.setText('无法获取版本清单')
        box.setInformativeText(msg)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()

    def rebuild(self):
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        self._rows = []
        if not self.versions:
            return
        q = self.search.text().strip().lower()
        cat = self.cat.currentText()
        mapped = {'全部': None, '正式版': 'release', '快照': 'snapshot', '旧版': 'old'}
        want = mapped.get(cat)
        rows = 0
        for v in self.versions:
            if want and v.get('type') != want:
                continue
            if q and q not in v['id'].lower():
                continue
            row = VersionRow(v, self)
            self.list_layout.addWidget(row)
            self._rows.append(row)
            rows += 1
        if rows == 0:
            self.list_layout.addWidget(QLabel('没有匹配的版本。'))
        self.list_layout.addStretch(1)
        if self._active_row is not None:
            self._set_rows_enabled(False)

    def _set_rows_enabled(self, on):
        for r in self._rows:
            if on:
                r._update_state()
            else:
                r.btn.setEnabled(False)

    # ---------------------------------------------------------- 安装（弹窗选加载器）
    def start_install(self, row):
        try:
            self._start_install(row)
        except Exception as e:
            import traceback
            msg = str(e) or repr(e)
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle('安装未能开始')
            box.setText('启动安装流程时出错：%s' % msg)
            box.setDetailedText(traceback.format_exc())
            box.setStandardButtons(QMessageBox.Ok)
            box.exec_()

    def _start_install(self, row):
        app = self.app
        source = app.settings['downloadSource']
        vid = row.version['id']
        vurl = row.version['url']
        self._install_vid = vid
        dlg = LoaderChoiceDialog(self, vid, source, app.data_root)
        if dlg.exec_() != QDialog.Accepted:
            return
        loaders = dlg.get_choices()
        self._active_row = row
        row.btn.setText('安装中...')
        self._set_rows_enabled(False)
        self.prog.show_stage('准备下载', '即将安装 Minecraft %s（含你选择的加载器）...' % vid)

        def on_progress(info):
            self.bridge.report.emit(info)

        def on_item(done, total, task, ok):
            self.bridge.report.emit({'kind': 'item', 'files_done': done,
                                     'files_total': total})

        def log(m):
            self.bridge.report.emit({'stage': m})

        results = []
        state = {'java_path': None, 'java_downloaded': False}

        def job():
            concurrency = app.settings.get('concurrency', 16)
            segmented = app.settings.get('segmented', True)
            # 先确保有合适的 Java：系统已有就用系统，没有就按 MC 版本自动下载
            from core.java import ensure_java_for_version
            java_path, java_downloaded = ensure_java_for_version(
                vid, app.data_root, source,
                on_progress=on_progress, log=log)
            state['java_path'] = java_path
            state['java_downloaded'] = java_downloaded
            log('正在安装原版基版本 %s（客户端、库与资源）...' % vid)
            install_vanilla(app.data_root, source, vid, vurl,
                           progress_cb=on_progress, item_cb=on_item,
                           concurrency=concurrency, segmented=segmented)
            for code, ver in loaders:
                disp = dict(LOADER_TYPES).get(code, code)
                log('正在安装 %s（%s / %s）...' % (disp, vid, ver))
                vid2 = install_loader(app.data_root, source, code, vid, ver,
                                     java_path=java_path, log=log,
                                     progress_cb=on_progress, item_cb=on_item,
                                     concurrency=concurrency, segmented=segmented)
                name = suggest_instance_name(code, vid, ver)
                create_instance(app.data_root, name, vid2, code)
                results.append((disp, name))
            return results

        w = Worker(job)
        self._install_worker = w
        w.done.connect(self._on_job_finished)
        w.error.connect(self.on_install_error)
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_job_finished(self, results):
        """worker 结束后在主线程执行：写回自动下载的 Java 路径"""
        self._java_path = state.get('java_path')
        self.on_install_done(results)

    def on_report(self, info):
        if not isinstance(info, dict):
            return
        if info.get('kind') == 'item':
            return
        self.prog.apply(info)

    def on_install_done(self, results):
        row = self._active_row
        self._active_row = None
        if row is not None:
            row._update_state()
        self._set_rows_enabled(True)
        # 若本次是自动下载的 Java 且用户没自定义过路径，写回设置（在主线程做）
        try:
            java_path = self._java_path
            if java_path and self.app.settings.get('javaPath', 'java') in ('java', ''):
                self.app.settings['javaPath'] = java_path
                from core.config import save_settings
                save_settings(self.app.settings)
        except Exception:
            pass
        if results:
            lines = '；'.join('%s（%s）' % (n, d) for d, n in results)
            self.prog.finish('安装完成', '已创建实例：%s。到「实例」页启动即可。' % lines)
        else:
            self.prog.finish('安装完成',
                             '原版 %s 已安装，到「实例」页创建实例即可启动。' % self._install_vid)
        try:
            self.app.refresh_instances_page()
        except Exception:
            pass
        from ui.toast import Toast
        if results:
            txt = '已安装：' + '、'.join(n for _, n in results)
        else:
            txt = '原版 %s 已安装' % self._install_vid
        self._toast = Toast(self, txt, 'success')
        g = self.mapToGlobal(QPoint(0, 18))
        self._toast.move(g.x() + (self.width() - self._toast.width()) // 2, g.y())
        self._toast.show()
        # 完成提醒：播放提示音 + 发系统通知
        try:
            from core.notify import notify_complete
            notify_complete('ZMCLauncher', '安装完成：' + txt,
                            self.app.settings, self.app)
        except Exception:
            pass
        QTimer.singleShot(4000, self._hide_progress)

    def on_install_error(self, e):
        self._active_row = None
        msg = str(e)
        head = msg.split('\n')[0]
        self.prog.show_stage('安装失败', head)
        self._set_rows_enabled(True)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle('安装失败')
        box.setText(head)
        if '\n' in msg:
            box.setInformativeText(msg[len(head):].strip())
        box.setStandardButtons(QMessageBox.Ok)
        box.exec_()

    def _hide_progress(self):
        if self._active_row is None:
            self.prog.setVisible(False)
