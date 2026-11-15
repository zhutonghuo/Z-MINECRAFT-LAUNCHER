import os
from concurrent.futures import ThreadPoolExecutor

from PyQt5.QtCore import Qt, QPoint, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QFrame, QLineEdit, QComboBox, QMessageBox,
                             QDialog, QCheckBox)

from core.instances import list_instances
from core.modrinth import (PROJECT_TYPES, search_projects, resolve_download,
                            target_path, fetch_icon)
from core.download import Progress, download_all
from ui.widgets import ProgressPanel, fmt_size
from ui.worker import Worker, Bridge
from ui.toast import Toast

ICON_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7',
               '#06b6d4', '#ec4899', '#84cc16']


class ModCard(QFrame):
    def __init__(self, hit, page):
        super().__init__()
        self.hit = hit
        self.page = page
        self.setObjectName('Card')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        self.icon = QLabel()
        self.icon.setFixedSize(46, 46)
        self.icon.setAlignment(Qt.AlignCenter)
        path = hit.get('icon_path')
        pm = QPixmap(path) if path and os.path.isfile(path) else QPixmap()
        if not pm.isNull():
            self.icon.setPixmap(pm.scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            color = ICON_COLORS[hash(hit.get('id', '')) % len(ICON_COLORS)]
            self.icon.setText((hit.get('title') or '?')[:1])
            self.icon.setStyleSheet(
                'background:%s;color:#fff;border-radius:10px;font-size:20px;font-weight:700;'
                % color)
        layout.addWidget(self.icon)
        info = QVBoxLayout()
        info.setSpacing(4)
        title = QLabel(hit.get('title') or hit.get('slug') or '')
        title.setObjectName('CardTitle')
        desc = QLabel(hit.get('description') or '')
        desc.setObjectName('CardSub')
        desc.setWordWrap(True)
        desc.setMaximumWidth(560)
        meta = QLabel('作者 %s   ·   下载 %s   ·   收藏 %s' % (
            hit.get('author') or '-', fmt_size(hit.get('downloads')), fmt_size(hit.get('follows'))))
        meta.setObjectName('PageHint')
        info.addWidget(title)
        info.addWidget(desc)
        info.addWidget(meta)
        layout.addLayout(info, 1)
        self.btn = QPushButton('安装')
        self.btn.setObjectName('InstallButton')
        self.btn.clicked.connect(lambda: self.page.install(self))
        layout.addWidget(self.btn, 0, Qt.AlignTop)


class InstallTargetDialog(QDialog):
    def __init__(self, parent, app, hit, ptype, instances):
        super().__init__(parent)
        self.app = app
        self.hit = hit
        self.ptype = ptype
        self.instances = instances
        self.results = []
        self.rows = []
        self.setWindowTitle('选择安装到哪些实例')
        self.setMinimumWidth(480)
        self.setMinimumHeight(380)
        layout = QVBoxLayout(self)
        tip = QLabel('勾选要安装到的实例（可多选）。已安装的实例会标注提示，重复安装时会被询问确认。')
        tip.setWordWrap(True)
        tip.setObjectName('PageHint')
        layout.addWidget(tip)
        self.scroll = QScrollArea()
        self.scroll.setObjectName('Scroll')
        self.scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(8)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        self._loading = QLabel('正在检测各实例的安装状态...')
        self._loading.setObjectName('PageHint')
        self.body_layout.addWidget(self._loading)
        btns = QHBoxLayout()
        self.btn_all = QPushButton('全选')
        self.btn_none = QPushButton('全不选')
        self.btn_all.setObjectName('GhostButton')
        self.btn_none.setObjectName('GhostButton')
        self.btn_all.clicked.connect(self._select_all)
        self.btn_none.clicked.connect(self._select_none)
        btns.addWidget(self.btn_all)
        btns.addWidget(self.btn_none)
        btns.addStretch(1)
        self.btn_ok = QPushButton('确定')
        self.btn_ok.setObjectName('PrimaryButton')
        self.btn_cancel = QPushButton('取消')
        self.btn_cancel.setObjectName('GhostButton')
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_ok)
        layout.addLayout(btns)
        self._load()

    def _load(self):
        hit = self.hit
        ptype = self.ptype
        instances = self.instances

        def job():
            out = []
            for inst in instances:
                try:
                    info = resolve_download(hit['id'], ptype, inst['versionId'])
                    dest = target_path(inst['gameDir'], ptype, info['filename'])
                    out.append({'inst': inst, 'info': info, 'dest': dest,
                                'installed': os.path.isfile(dest), 'error': None})
                except Exception as e:
                    out.append({'inst': inst, 'info': None, 'dest': None,
                                'installed': False, 'error': str(e)})
            return out

        w = Worker(job)
        w.done.connect(self._on_loaded)
        w.error.connect(lambda e: self._on_loaded([]))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_loaded(self, results):
        self.results = results
        self._loading.deleteLater()
        for r in results:
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(2, 4, 2, 4)
            rl.setSpacing(2)
            inst = r['inst']
            cb = QCheckBox('%s  (%s)' % (inst['name'], inst['versionId']))
            rl.addWidget(cb)
            if r['installed']:
                cb.setChecked(False)
                cb.setStyleSheet('color:#888')
                sub = QLabel('（已安装，无需重复安装）')
                sub.setObjectName('PageHint')
                rl.addWidget(sub)
            elif r['error']:
                cb.setChecked(False)
                cb.setStyleSheet('color:#c0392b')
                sub = QLabel('（无兼容版本）')
                sub.setObjectName('PageHint')
                rl.addWidget(sub)
            else:
                cb.setChecked(True)
            self.body_layout.addWidget(row)
            self.rows.append((r, cb))
        self.body_layout.addStretch(1)

    def _select_all(self):
        for _, cb in self.rows:
            cb.setChecked(True)

    def _select_none(self):
        for _, cb in self.rows:
            cb.setChecked(False)

    def selected(self):
        out = []
        for r, cb in self.rows:
            if cb.isChecked() and r['info'] is not None:
                out.append(r)
        return out


class ModPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName('Page')
        self._cards = []
        self._instances = []
        self._active = None
        self._active_hit = None
        self._active_ptype = None
        self._queue = []
        self._done = []
        self.bridge = Bridge()
        self.bridge.report.connect(self.on_report)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        head = QHBoxLayout()
        title = QLabel('模组')
        title.setObjectName('PageTitle')
        head.addWidget(title)
        head.addStretch(1)
        self.inst_combo = QComboBox()
        self.inst_combo.setObjectName('ComboBox')
        self.inst_combo.setMinimumWidth(170)
        self.cat_combo = QComboBox()
        self.cat_combo.setObjectName('ComboBox')
        for code, name in PROJECT_TYPES:
            self.cat_combo.addItem(name, code)
        self.search = QLineEdit()
        self.search.setObjectName('LineEdit')
        self.search.setPlaceholderText('搜索 Modrinth 项目（留空看热门）...')
        self.search.returnPressed.connect(self.do_search)
        self.btn = QPushButton('搜索')
        self.btn.setObjectName('PrimaryButton')
        self.btn.clicked.connect(self.do_search)
        head.addWidget(QLabel('基准版本'))
        head.addWidget(self.inst_combo)
        head.addWidget(QLabel('类型'))
        head.addWidget(self.cat_combo)
        head.addWidget(self.search)
        head.addWidget(self.btn)
        layout.addLayout(head)

        self.prog = ProgressPanel()
        layout.addWidget(self.prog)

        self.status_lbl = QLabel('从 Modrinth 搜索模组、资源包与光影，一键装进你的实例。')
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
        self.refresh_instances()
        self.do_search()

    def refresh_instances(self):
        self._instances = list_instances(self.app.data_root)
        self.inst_combo.clear()
        for inst in self._instances:
            self.inst_combo.addItem(inst['name'] + '  (' + inst['versionId'] + ')', inst)

    def current_instance(self):
        idx = self.inst_combo.currentIndex()
        if idx < 0 or idx >= len(self._instances):
            return None
        return self._instances[idx]

    def project_type(self):
        return self.cat_combo.currentData() or 'mod'

    def do_search(self):
        if not self._instances:
            self.status_lbl.setText('请先到「实例」页创建一个实例，才能安装模组。')
            self._clear_results()
            return
        inst = self.current_instance()
        query = self.search.text().strip()
        ptype = self.project_type()
        mc = inst['versionId'] if inst else ''
        self.status_lbl.setText('正在搜索 Modrinth...')
        self.btn.setEnabled(False)

        def job():
            data = search_projects(query, ptype, mc, limit=24)
            cache = os.path.join(self.app.data_root, 'cache', 'icons')
            os.makedirs(cache, exist_ok=True)

            def grab(h):
                url = h.get('icon_url')
                if not url:
                    return
                ext = '.jpg' if url.lower().endswith(('.jpg', '.jpeg')) else '.png'
                path = os.path.join(cache, h['id'] + ext)
                if not os.path.isfile(path):
                    fetch_icon(url, path)
                h['icon_path'] = path

            with ThreadPoolExecutor(max_workers=8) as ex:
                list(ex.map(grab, data['hits']))
            return data

        w = Worker(job)
        self._search_worker = w
        w.done.connect(self.on_search_done)
        w.error.connect(self.on_search_error)
        w.finished.connect(w.deleteLater)
        w.start()

    def _clear_results(self):
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        self._cards = []

    def on_search_done(self, data):
        self.btn.setEnabled(True)
        self._clear_results()
        hits = data.get('hits') or []
        if not hits:
            self.status_lbl.setText('没有找到相关项目，换个关键词试试。')
            return
        self.status_lbl.setText('共 %d 个结果（已按 %s 过滤）' % (
            data.get('total', len(hits)), self.cat_combo.currentText()))
        for h in hits:
            card = ModCard(h, self)
            self.list_layout.addWidget(card)
            self._cards.append(card)
        self.list_layout.addStretch(1)

    def on_search_error(self, e):
        self.btn.setEnabled(True)
        self.status_lbl.setText('搜索失败: ' + str(e))

    def install(self, card):
        if not self._instances:
            QMessageBox.warning(self, '提示', '请先到「实例」页创建一个实例，才能安装模组。')
            return
        ptype = self.project_type()
        hit = card.hit
        if len(self._instances) == 1:
            self._resolve_single(card, hit, ptype, self._instances[0])
            return
        dlg = InstallTargetDialog(self, self.app, hit, ptype, self._instances)
        if dlg.exec_() == QDialog.Accepted:
            targets = dlg.selected()
            if not targets:
                return
            self._begin_install(card, hit, ptype, targets)

    def _resolve_single(self, card, hit, ptype, inst):
        self._active = card
        self._active_hit = hit
        self._active_ptype = ptype
        card.btn.setEnabled(False)
        card.btn.setText('检测中...')
        self.prog.show_stage('准备', '正在确认 %s 是否已安装...' % inst['name'])

        def job():
            info = resolve_download(hit['id'], ptype, inst['versionId'])
            dest = target_path(inst['gameDir'], ptype, info['filename'])
            return {'inst': inst, 'info': info, 'dest': dest,
                    'installed': os.path.isfile(dest), 'error': None}

        w = Worker(job)
        w.done.connect(lambda r: self._begin_install(card, hit, ptype, [r]))
        w.error.connect(lambda e: self._on_resolve_error(card, e))
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_resolve_error(self, card, e):
        card.btn.setEnabled(True)
        card.btn.setText('安装')
        self.prog.show_stage('无法安装', str(e))
        QMessageBox.warning(self, '无法安装', str(e))

    def _begin_install(self, card, hit, ptype, targets):
        self._active = card
        self._active_hit = hit
        self._active_ptype = ptype
        card.btn.setEnabled(False)
        card.btn.setText('安装中...')
        ready = [t for t in targets if t['info'] is not None]
        if not ready:
            card.btn.setEnabled(True)
            card.btn.setText('安装')
            QMessageBox.warning(self, '无法安装', '所选实例均无兼容版本，无法安装该模组。')
            return
        installed = [t for t in ready if t.get('installed')]
        if installed:
            names = '、'.join(t['inst']['name'] for t in installed)
            ans = QMessageBox.question(self, '重复安装确认',
                                      '以下 %d 个实例已安装此模组：\n%s\n\n仍要重复安装吗？'
                                      % (len(installed), names),
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ans == QMessageBox.No:
                ready = [t for t in ready if not t.get('installed')]
                if not ready:
                    card.btn.setEnabled(True)
                    card.btn.setText('安装')
                    return
        self._queue = ready
        self._done = []
        self._install_next(card, hit, ptype)

    def _install_next(self, card, hit, ptype):
        if not self._queue:
            self._finish_all(card, hit, ptype)
            return
        t = self._queue[0]
        inst = t['inst']
        info = t['info']
        total = len(self._queue) + len(self._done)
        card.btn.setText('安装中... (%d/%d)' % (len(self._done) + 1, total))
        self.prog.show_stage('准备下载', '正在下载到实例「%s」...' % inst['name'])

        def on_progress(p):
            self.bridge.report.emit(p)

        def job():
            task = {'url': info['url'], 'dest': t['dest'], 'sha1': info['sha1'],
                    'size': info['size']}
            prog = Progress(info['size'], '下载 ' + info['filename'])
            download_all([task], concurrency=self.app.settings.get('concurrency', 16),
                         segmented=self.app.settings.get('segmented', True),
                         progress_cb=on_progress, prog=prog,
                         stage='下载 ' + (hit.get('title') or info['filename']))
            return {'dest': t['dest'], 'version': info['version'], 'title': hit.get('title'),
                    'folder': info['folder'], 'inst': inst['name']}

        w = Worker(job)
        w.done.connect(self._on_one_done)
        w.error.connect(self._on_one_error)
        w.finished.connect(w.deleteLater)
        w.start()

    def _on_one_done(self, res):
        self._done.append(res)
        if self._queue:
            self._queue.pop(0)
        self.prog.finish('安装完成', '已保存到 %s/%s/%s' % (
            res.get('inst'), res.get('folder'), os.path.basename(res.get('dest') or '')))
        self._install_next(self._active, self._active_hit, self._active_ptype)

    def _on_one_error(self, e):
        failed = self._queue.pop(0) if self._queue else None
        name = failed['inst']['name'] if failed else ''
        QMessageBox.warning(self, '安装失败',
                            str(e) + (('（实例：' + name + '）') if name else ''))
        self.prog.show_stage('安装失败', str(e))
        self._install_next(self._active, self._active_hit, self._active_ptype)

    def _finish_all(self, card, hit, ptype):
        card.btn.setEnabled(True)
        card.btn.setText('安装')
        n = len(self._done)
        if n:
            self._toast('安装成功：%s（%d 个实例）' % (hit.get('title') or '', n))
            try:
                from core.notify import notify_complete
                notify_complete('ZMCLauncher',
                                '安装完成：' + (hit.get('title') or '') + '（%d 个实例）' % n,
                                self.app.settings, self.app)
            except Exception:
                pass
        self._active = None
        self._active_hit = None
        self._active_ptype = None
        QTimer.singleShot(4000, self._hide_progress)

    def on_report(self, info):
        if not isinstance(info, dict):
            return
        self.prog.apply(info)

    def _hide_progress(self):
        if self._active is None:
            self.prog.setVisible(False)

    def _toast(self, text):
        t = Toast(self, text, 'success')
        self._toast_widget = t
        p = self.mapToGlobal(QPoint(0, 18))
        t.move(p.x() + (self.width() - t.width()) // 2, p.y())
        t.show()
