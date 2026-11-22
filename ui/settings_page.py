import os
import sys
import tempfile

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QLineEdit, QComboBox, QSpinBox, QFrame, QCheckBox,
                             QScrollArea, QApplication, QSizePolicy, QFileDialog,
                             QMessageBox)
from PyQt5.QtCore import Qt

from core.java import detect_java_runtimes
from core.config import DOWNLOAD_SOURCES
from core.appinfo import LAUNCHER_VERSION, is_newer
from ui.worker import Worker, Bridge
from ui.updater import fetch_version_info, UpdateProgressDialog


class Row(QFrame):
    def __init__(self, label, widget):
        super().__init__()
        self.setObjectName('SettingRow')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        l = QLabel(label)
        l.setObjectName('SettingLabel')
        l.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        layout.addWidget(l)
        layout.addSpacing(12)
        # 输入框撑满剩余宽度，避免被拉伸空白挤成一条
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(widget, 1)


class SettingsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName('Page')
        s = app.settings

        # 用滚动区域包裹内容：避免内容过多时被 QStackedWidget 在固定高度下压扁
        scroll = QScrollArea(self)
        scroll.setObjectName('Scroll')
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName('PageScroll')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(8)
        title = QLabel('设置')
        title.setObjectName('PageTitle')
        layout.addWidget(title)
        layout.addSpacing(8)

        self.java_edit = QLineEdit()
        self.java_edit.setObjectName('LineEdit')
        self.java_edit.setText(s.get('javaPath', 'java'))
        detect_btn = QPushButton('自动检测')
        detect_btn.setObjectName('ThemeButton')
        detect_btn.clicked.connect(self.detect_java)
        java_row = Row('Java 路径', self.java_edit)
        java_row.layout().addWidget(detect_btn)
        layout.addWidget(java_row)

        self.min_spin = QSpinBox()
        self.min_spin.setRange(256, 65536)
        self.min_spin.setSingleStep(128)
        self.min_spin.setValue(s.get('minMemory', 512))
        self.min_spin.setObjectName('Spin')
        self.max_spin = QSpinBox()
        self.max_spin.setRange(512, 65536)
        self.max_spin.setSingleStep(256)
        self.max_spin.setValue(s.get('maxMemory', 2048))
        self.max_spin.setObjectName('Spin')
        mem_row = Row('内存 (最小/最大 MB)', self.min_spin)
        mem_row.layout().addWidget(self.max_spin)
        layout.addWidget(mem_row)

        self.source_combo = QComboBox()
        self.source_combo.setObjectName('ComboBox')
        self.source_map = {}
        for key, val in DOWNLOAD_SOURCES.items():
            self.source_combo.addItem(val['name'])
            self.source_map[val['name']] = key
        idx = self.source_combo.findText(DOWNLOAD_SOURCES.get(s.get('downloadSource', 'bmclapi'), {}).get('name', ''))
        if idx >= 0:
            self.source_combo.setCurrentIndex(idx)
        layout.addWidget(Row('下载镜像源', self.source_combo))

        self.custom_edit = QLineEdit()
        self.custom_edit.setObjectName('LineEdit')
        self.custom_edit.setPlaceholderText('填写你的镜像根地址，例如 https://mirror.example.com')
        self.custom_edit.setText(s.get('customSourceUrl', ''))
        self.custom_row = Row('自定义镜像地址', self.custom_edit)
        self.custom_row.setVisible(s.get('downloadSource') == 'custom')
        layout.addWidget(self.custom_row)
        self.source_combo.currentTextChanged.connect(self._on_source_changed)

        src_hint = QLabel('提示：镜像节点不稳定时会自动重试并降级到官方源下载。')
        src_hint.setObjectName('Hint')
        src_hint.setWordWrap(True)
        layout.addWidget(src_hint)

        self.src_status = QLabel('')
        self.src_status.setObjectName('Hint')
        self.src_status.setWordWrap(True)
        layout.addWidget(self.src_status)

        test_btn = QPushButton('测试下载源')
        test_btn.setObjectName('PrimaryButton')
        test_btn.clicked.connect(self.test_source)
        layout.addWidget(test_btn)

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName('ComboBox')
        # 显示中文，itemData 存代码用的键值
        self.theme_combo.addItem('龙猫蓝（浅色）', 'light')
        self.theme_combo.addItem('深空蓝（深色）', 'dark')
        cur_theme = s.get('theme', 'light')
        ti = self.theme_combo.findData(cur_theme)
        if ti >= 0:
            self.theme_combo.setCurrentIndex(ti)
        self.theme_combo.currentIndexChanged.connect(
            lambda i: app.set_theme(self.theme_combo.itemData(i)) if i >= 0 else None)
        layout.addWidget(Row('主题', self.theme_combo))

        self.msa_edit = QLineEdit()
        self.msa_edit.setObjectName('LineEdit')
        self.msa_edit.setPlaceholderText('留空则使用内置默认 ID')
        self.msa_edit.setText(s.get('msaClientId', ''))
        layout.addWidget(Row('微软客户端ID（可选）', self.msa_edit))

        self.ygg_edit = QLineEdit()
        self.ygg_edit.setObjectName('LineEdit')
        self.ygg_edit.setPlaceholderText('如 https://littleskin.cn/api/yggdrasil')
        self.ygg_edit.setText(s.get('yggServer', ''))
        layout.addWidget(Row('第三方登录服务器', self.ygg_edit))

        ygg_hint = QLabel('留空表示不使用第三方服务器。填写后可在「账号管理」里用'
                          '用户名密码登录该服务器，账号会自动带 authlib-injector 启动。')
        ygg_hint.setObjectName('Hint')
        ygg_hint.setWordWrap(True)
        layout.addWidget(ygg_hint)

        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 32)
        self.conc_spin.setValue(s.get('concurrency', 16))
        self.conc_spin.setToolTip('同时进行的下载连接数，越大越快；过高可能被下载源限流')
        self.conc_spin.setObjectName('Spin')
        layout.addWidget(Row('下载并发数（1-32）', self.conc_spin))

        self.seg_check = QCheckBox('大文件分段并行下载（单文件最多 8 段同时下，明显提速大体积文件）')
        self.seg_check.setChecked(s.get('segmented', True))
        self.seg_check.setObjectName('CheckBox')
        layout.addWidget(self.seg_check)

        self.stage_check = QCheckBox('显示「启动进度台」（实时显示当前步骤与已运行耗时，'
                                     '即使游戏日志为空也能看到进度，推荐开启）')
        self.stage_check.setChecked(s.get('showStagePanel', True))
        self.stage_check.setObjectName('CheckBox')
        layout.addWidget(self.stage_check)

        self.onboard_check = QCheckBox('跳过首次启动引导页（新建实例首次进入时的'
                                       '「Welcome to Minecraft」向导，直接进主菜单）')
        self.onboard_check.setChecked(s.get('skipOnboarding', True))
        self.onboard_check.setObjectName('CheckBox')
        layout.addWidget(self.onboard_check)

        layout.addSpacing(12)
        visual_head = QLabel('视觉')
        visual_head.setObjectName('CardTitle')
        layout.addWidget(visual_head)

        self.elastic_check = QCheckBox('弹性视觉（切换页面、弹窗等场景带弹性动画，让应用更有活力）')
        self.elastic_check.setChecked(s.get('elastic', True))
        self.elastic_check.setObjectName('CheckBox')
        layout.addWidget(self.elastic_check)

        layout.addSpacing(12)
        notify_head = QLabel('完成提醒')
        notify_head.setObjectName('CardTitle')
        layout.addWidget(notify_head)

        self.notify_sound_check = QCheckBox('安装版本、下载完成后播放提示音')
        self.notify_sound_check.setChecked(s.get('notifySound', True))
        self.notify_sound_check.setObjectName('CheckBox')
        layout.addWidget(self.notify_sound_check)

        self.notify_toast_check = QCheckBox('安装版本、下载完成后发送系统通知（Windows 通知中心）')
        self.notify_toast_check.setChecked(s.get('notifyToast', True))
        self.notify_toast_check.setObjectName('CheckBox')
        layout.addWidget(self.notify_toast_check)

        self._notify_hint = QLabel('两项开关互相独立，关闭其中一项不影响另一项。')
        self._notify_hint.setObjectName('Hint')
        self._notify_hint.setWordWrap(True)
        layout.addWidget(self._notify_hint)

        test_notify_row = QHBoxLayout()
        test_notify_btn = QPushButton('试一下提醒效果')
        test_notify_btn.setObjectName('GhostButton')
        test_notify_btn.clicked.connect(self._test_notify)
        test_notify_row.addWidget(test_notify_btn)
        test_notify_row.addStretch(1)
        layout.addLayout(test_notify_row)

        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName('ComboBox')
        self.lang_map = {
            '中文（简体）': 'zh_cn',
            '中文（繁体）': 'zh_tw',
            'English': 'en_us',
        }
        self.lang_combo.addItems(list(self.lang_map.keys()))
        cur_lang = s.get('gameLang', 'zh_cn')
        for i, code in enumerate(self.lang_map.values()):
            if code == cur_lang:
                self.lang_combo.setCurrentIndex(i)
                break
        self.lang_combo.setToolTip('游戏内界面语言（写入实例的 options.txt，'
                                    '下次启动生效；中文语言包需已下载）')
        layout.addWidget(Row('游戏界面语言', self.lang_combo))

        self.proxy_combo = QComboBox()
        self.proxy_combo.setObjectName('ComboBox')
        self.proxy_combo.addItems(['跟随系统', '不使用代理', '自定义'])
        proxy_mode = s.get('proxyMode', 'system')
        pi = {'system': 0, 'none': 1}.get(proxy_mode, 2)
        self.proxy_combo.setCurrentIndex(pi)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setObjectName('LineEdit')
        self.proxy_edit.setPlaceholderText('例如 http://127.0.0.1:7890')
        self.proxy_edit.setText(s.get('proxyUrl', ''))
        self.proxy_edit.setEnabled(pi == 2)
        self.proxy_combo.currentIndexChanged.connect(
            lambda i: self.proxy_edit.setEnabled(i == 2))
        layout.addWidget(Row('网络代理', self.proxy_combo))
        layout.addWidget(Row('代理地址', self.proxy_edit))

        layout.addSpacing(12)
        self.data_dir_edit = QLineEdit()
        self.data_dir_edit.setObjectName('LineEdit')
        self.data_dir_edit.setText(app.data_root)
        browse_dd = QPushButton('浏览...')
        browse_dd.setObjectName('GhostButton')
        browse_dd.clicked.connect(self._browse_data_dir)
        detect_dd = QPushButton('自动检测')
        detect_dd.setObjectName('ThemeButton')
        detect_dd.setToolTip('扫描本机，找出其它版本启动器已经用过的数据文件夹')
        detect_dd.clicked.connect(self._detect_data_dir)
        dd_row = Row('启动器数据文件夹', self.data_dir_edit)
        dd_row.layout().addWidget(browse_dd)
        dd_row.layout().addWidget(detect_dd)
        layout.addWidget(dd_row)
        self.dd_status = QLabel('')
        self.dd_status.setObjectName('Hint')
        self.dd_status.setWordWrap(True)
        layout.addWidget(self.dd_status)
        self.migrate_btn = QPushButton('迁移并应用')
        self.migrate_btn.setObjectName('PrimaryButton')
        self.migrate_btn.clicked.connect(self._migrate)
        layout.addWidget(self.migrate_btn)
        dd_hint = QLabel('修改后点「迁移并应用」会把当前文件夹里的全部数据'
                        '（账号、游戏版本、库、资源、日志等）自动移动到新位置，'
                        '旧文件夹会被清空并记住新位置。迁移在后台进行，大目录可能需几分钟。')
        dd_hint.setObjectName('Hint')
        dd_hint.setWordWrap(True)
        layout.addWidget(dd_hint)

        layout.addSpacing(12)
        # ---------- 检查更新 ----------
        upd_head = QLabel('更新')
        upd_head.setObjectName('PageTitle')
        upd_head.setStyleSheet('font-size:15px;font-weight:700;margin-top:4px')
        layout.addWidget(upd_head)

        cur_ver_row = QHBoxLayout()
        ver_label = QLabel('当前版本：%s' % LAUNCHER_VERSION)
        ver_label.setObjectName('SettingLabel')
        check_btn = QPushButton('检查更新')
        check_btn.setObjectName('ThemeButton')
        check_btn.clicked.connect(self.check_update)
        cur_ver_row.addWidget(ver_label)
        cur_ver_row.addSpacing(12)
        cur_ver_row.addWidget(check_btn)
        cur_ver_row.addStretch(1)
        layout.addLayout(cur_ver_row)

        self.update_status = QLabel('')
        self.update_status.setObjectName('Hint')
        self.update_status.setWordWrap(True)
        layout.addWidget(self.update_status)

        self.update_notes = QLabel('')
        self.update_notes.setObjectName('Hint')
        self.update_notes.setWordWrap(True)
        self.update_notes.hide()
        layout.addWidget(self.update_notes)

        self.update_btn = QPushButton('一键更新（推荐）')
        self.update_btn.setObjectName('PrimaryButton')
        self.update_btn.clicked.connect(self.do_inplace_update)
        self.update_btn.hide()
        layout.addWidget(self.update_btn)

        self.dl_setup_btn = QPushButton('下载安装包手动更新')
        self.dl_setup_btn.setObjectName('GhostButton')
        self.dl_setup_btn.clicked.connect(lambda: self.download_update('setup'))
        self.dl_setup_btn.hide()
        layout.addWidget(self.dl_setup_btn)

        self.dl_portable_btn = QPushButton('下载绿色版手动更新')
        self.dl_portable_btn.setObjectName('GhostButton')
        self.dl_portable_btn.clicked.connect(lambda: self.download_update('portable'))
        self.dl_portable_btn.hide()
        layout.addWidget(self.dl_portable_btn)

        layout.addSpacing(12)
        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('PrimaryButton')
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

    def _on_source_changed(self, text):
        """下载源切到「自定义」时显示镜像地址输入框，否则隐藏。"""
        self.custom_row.setVisible(text == '自定义')

    def _browse_data_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, '选择新的启动器数据文件夹',
            self.data_dir_edit.text() or os.path.expanduser('~'))
        if d:
            self.data_dir_edit.setText(d)

    def _detect_data_dir(self):
        """扫描本机，找出其它版本启动器用过的数据文件夹。

        结果只填进输入框供用户查看/手动确认，绝不自动迁移。
        扫描要读盘，放后台线程，避免卡住界面。
        """
        self.dd_status.setText('正在检测本机已有的启动器数据...')
        QApplication.processEvents()
        from ui.worker import Worker, Bridge
        # 把后台结果安全地转回主线程再操作 UI
        if not hasattr(self, 'bridge'):
            self.bridge = Bridge()
            self.bridge.report.connect(self._on_detected)
        w = Worker(self._scan_worker)
        # 必须持有引用：QThread 运行中被 GC 回收会让 Qt 直接 abort（无报错闪退）
        self._detect_worker = w
        w.done.connect(lambda c: self.bridge.report.emit(('ok', c)))
        w.error.connect(lambda e: self.bridge.report.emit(('err', str(e))))
        w.start()

    def _scan_worker(self):
        from core.config import find_existing_data_dirs
        return find_existing_data_dirs(include=self.app.data_root)

    def _on_detected(self, payload):
        """主线程槽：处理后台扫描结果。payload = ('ok', cands) 或 ('err', msg)"""
        if payload[0] == 'err':
            self.dd_status.setText('检测失败：%s' % payload[1])
            return
        self._apply_detected(payload[1])

    def _apply_detected(self, cands):
        """把检测结果填进输入框并给出说明（不自动迁移）。"""
        cur = os.path.normcase(os.path.abspath(self.app.data_root))
        # 当前正在用的目录排最前，其余按可信度排序
        others = [c for c in cands if os.path.normcase(c['path']) != cur]
        # 本启动器自己的目录优先展示；其它启动器的目录只是「可选目标」
        own = [c for c in others if c.get('own')]
        foreign = [c for c in others if not c.get('own')]
        if not others:
            if cands:
                self.dd_status.setText('当前使用的就是已检测到的启动器数据文件夹：'
                                       + self.app.data_root)
            else:
                self.dd_status.setText('本机未检测到其它启动器使用过的数据文件夹。')
            return
        best = (own + foreign)[0]
        # 只把路径填进输入框，不自动迁移、不自动切换
        self.data_dir_edit.setText(best['path'])
        detail = []
        if best.get('versions'):
            detail.append('%d 个版本' % best['versions'])
        if best.get('accounts'):
            detail.append('%d 个账号' % best['accounts'])
        if best.get('libraries'):
            detail.append('已有依赖库')
        if best.get('assets'):
            detail.append('已有资源文件')
        extra = ('（' + '、'.join(detail) + '）') if detail else ''
        if best.get('own'):
            head = '已检测到本启动器其它版本使用过的数据文件夹%s：%s\n' % (
                extra, best['path'])
            tail = '路径已填入上方输入框，确认无误后点「迁移并应用」即可切换；不点则保持现状。'
        else:
            head = ('已检测到别的启动器（如官方启动器）的数据目录%s：%s\n' % (
                extra, best['path']))
            tail = ('其游戏版本与依赖库结构与本启动器兼容，但账号格式不同，'
                    '不会自动沿用。路径已填入上方输入框，确认无误后点'
                    '「迁移并应用」即可切换；不点则保持现状。')
        text = head + tail
        if len(own) > 1 or foreign:
            others_txt = '、'.join(c['path'] for c in (own[1:] + foreign)[:3])
            text += '\n另外还找到：' + others_txt
        self.dd_status.setText(text)

    def showEvent(self, event):
        """进入设置页时自动定位一次：把找到的路径填进输入框，但绝不自动确认。"""
        super().showEvent(event)
        if getattr(self, '_detected_once', False):
            return
        self._detected_once = True
        # 启动时若已自动沿用某个目录，直接说明即可，无需再扫盘
        auto = getattr(self.app, 'auto_adopted_data_dir', None)
        if auto:
            self.data_dir_edit.setText(auto)
            self.dd_status.setText(
                '已自动沿用其它版本启动器的数据文件夹：%s\n'
                '（检测到其中已有可用的启动器数据，已直接继续使用，'
                '无需手动确认）' % auto)
            return
        self._detect_data_dir()

    def _migrate(self):
        """把数据目录迁移到用户指定的新位置（后台线程执行）。"""
        new = self.data_dir_edit.text().strip()
        if not new:
            self.app.window.show_toast('请先选择目标文件夹', 'error')
            return
        if os.path.abspath(new) == os.path.abspath(self.app.data_root):
            self.app.window.show_toast('已是当前位置', 'info')
            return
        # 目标若是其它版本启动器用过的目录，说明是「合并」而不是「搬家」
        extra = ''
        try:
            from core.config import inspect_data_dir
            info = inspect_data_dir(os.path.abspath(new))
        except Exception:
            info = None
        if info and info.get('usable'):
            bits = []
            if info.get('versions'):
                bits.append('%d 个版本' % info['versions'])
            if info.get('accounts'):
                bits.append('%d 个账号' % info['accounts'])
            if info.get('libraries'):
                bits.append('依赖库')
            if info.get('assets'):
                bits.append('资源文件')
            if bits:
                extra = ('\n\n⚠ 目标位置已有启动器数据（%s），'
                         '本次为合并：同名文件保留目标位置的，'
                         '其余内容会移入。' % '、'.join(bits))
        r = QMessageBox.question(
            self, '确认迁移',
            '将把当前启动器数据文件夹的全部内容移动到：\n%s\n\n'
            '移动后旧文件夹会被清空，此操作不可撤销。是否继续？%s'
            % (new, extra),
            QMessageBox.Yes | QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.migrate_btn.setEnabled(False)
        self.app.window.show_toast('正在迁移数据，请稍候...', 'info')
        QApplication.processEvents()
        from ui.worker import Worker
        w = Worker(lambda: self.app.migrate_data_dir(new))
        # 必须持有引用：QThread 运行中被 GC 回收会让 Qt 直接 abort（无报错闪退）
        self._migrate_worker = w
        w.done.connect(self._on_migrated)
        w.error.connect(self._on_migrate_error)
        w.start()

    def _on_migrated(self, new_root):
        self.migrate_btn.setEnabled(True)
        self.data_dir_edit.setText(self.app.data_root)
        try:
            self.app.refresh_accounts()
            self.app.refresh_instances_page()
        except Exception:
            pass
        self.app.window.show_toast('数据已迁移到新位置', 'success')
        try:
            self.app.save_settings()
        except Exception:
            pass

    def _on_migrate_error(self, err):
        self.migrate_btn.setEnabled(True)
        self.app.window.show_toast('迁移失败：%s' % err, 'error')

    def detect_java(self):
        runtimes = detect_java_runtimes()
        if runtimes:
            self.java_edit.setText(runtimes[0]['path'])
        else:
            self.java_edit.setText('java')

    def test_source(self):
        """实测当前镜像源与官方源的可用性和速度"""
        from core.http import get_with_retry, friendly_error
        import time
        key = self.source_map.get(self.source_combo.currentText(), 'bmclapi')
        from core.config import rewrite_url
        from core.manifest import MANIFEST_URL

        if key == 'custom' and not self.custom_edit.text().strip():
            self.src_status.setText('自定义镜像地址为空，请先填写后再测试')
            return

        self.src_status.setText('正在测试...')
        QApplication.processEvents()
        mirror = rewrite_url(MANIFEST_URL, key)
        results = []
        for label, url in (('当前镜像', mirror), ('官方源', MANIFEST_URL)):
            t0 = time.time()
            try:
                r = get_with_retry(url, tries=2, timeout=15)
                dt = time.time() - t0
                n = len(r.content)
                results.append('%s：可用 ✓  %.1f KB / %.1fs' % (label, n / 1024, dt))
            except Exception as e:
                results.append('%s：不可用 ✗  %s' % (label, friendly_error(e)))
        self.src_status.setText('　|　'.join(results))

    def _test_notify(self):
        """试一下提醒效果：按当前勾选状态播放提示音并发系统通知"""
        from core.notify import notify_complete, play_notify_sound, _bundled_sound
        s = dict(self.app.settings)
        s['notifySound'] = self.notify_sound_check.isChecked()
        s['notifyToast'] = self.notify_toast_check.isChecked()
        played, notified = notify_complete('ZMCLauncher', '这是一条测试提醒，完成后你会看到我。',
                                           s, self.app)
        if not s['notifySound'] and not s['notifyToast']:
            self._notify_hint.setText('两项开关都已关闭，所以什么也不会发生。')
            return
        bits = []
        if s['notifySound']:
            bits.append('提示音已播放' if played else '提示音播放失败（缺少音频文件？）')
        if s['notifyToast']:
            bits.append('系统通知已发送' if notified else '系统通知发送失败')
        self._notify_hint.setText('　|　'.join(bits))

    # ---------- 检查更新 ----------
    def _downloads_dir(self):
        try:
            from PyQt5.QtCore import QStandardPaths
            d = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
            if d:
                return d
        except Exception:
            pass
        return os.path.expanduser('~')

    def check_update(self):
        """拉取服务器版本信息，比较后告知用户是否有新版本。"""
        self.update_status.setText('正在检查更新...')
        self.update_notes.hide()
        self.dl_setup_btn.hide()
        self.dl_portable_btn.hide()
        QApplication.processEvents()
        if not hasattr(self, 'ubridge'):
            self.ubridge = Bridge()
            self.ubridge.report.connect(self._on_update_checked)
        w = Worker(self._check_worker)
        # 强引用，避免 QThread 被 GC 回收导致闪退
        self._check_worker = w
        w.done.connect(lambda r: self.ubridge.report.emit(('ok', r)))
        w.error.connect(lambda e: self.ubridge.report.emit(('err', str(e))))
        w.start()

    def _check_worker(self):
        return fetch_version_info()

    def _on_update_checked(self, payload):
        """主线程槽：处理检查结果。payload = ('ok', info) 或 ('err', msg)"""
        if payload[0] == 'err':
            self.update_status.setText('检查更新失败：' + payload[1])
            return
        info = payload[1]
        remote = info.get('latest') or info.get('version')
        if not remote:
            self.update_status.setText('服务器返回的版本信息不完整，无法判断。')
            return
        self._latest_info = info
        assets = info.get('assets') or {}
        self._pending_assets = assets
        if is_newer(remote, LAUNCHER_VERSION):
            notes = info.get('notes') or info.get('releaseNotes') or ''
            self.update_status.setText(
                '发现新版本 v%s（当前 v%s）' % (remote, LAUNCHER_VERSION))
            if notes:
                self.update_notes.setText('更新内容：\n' + notes)
                self.update_notes.show()
            else:
                self.update_notes.hide()
            self.update_status.setText(
                '发现新版本 v%s（当前 v%s）' % (remote, LAUNCHER_VERSION))
            if notes:
                self.update_notes.setText('更新内容：\n' + notes)
                self.update_notes.show()
            else:
                self.update_notes.hide()
            # 主推「一键更新（就地替换，无需重装）」；安装包/绿色版作为手动兜底
            self.update_btn.setVisible(True)
            self.dl_setup_btn.setVisible(bool(assets.get('setup', {}).get('url')))
            self.dl_portable_btn.setVisible(bool(assets.get('portable', {}).get('url')))
        else:
            self.update_status.setText('已是最新版本（v%s）' % LAUNCHER_VERSION)
            self.update_notes.hide()
            self.update_btn.hide()
            self.dl_setup_btn.hide()
            self.dl_portable_btn.hide()

    def download_update(self, kind):
        """先问用户把安装包放哪，再用启动器内置下载功能拉取。"""
        info = getattr(self, '_latest_info', None)
        if not info:
            return
        assets = getattr(self, '_pending_assets', None) or info.get('assets') or {}
        asset = assets.get(kind) or {}
        url = asset.get('url')
        if not url:
            self.app.window.show_toast('版本信息中缺少该下载地址', 'error')
            return
        default_name = (os.path.basename(url) or
                        ('ZMCLauncher_Setup.exe' if kind == 'setup'
                         else 'ZMINECRAFTLAUNCHER.exe'))
        d = QFileDialog.getSaveFileName(
            self, '把 %s 保存到哪里？' % default_name,
            os.path.join(self._downloads_dir(), default_name),
            '安装程序 (*.exe);;所有文件 (*.*)')
        if not d or not d[0]:
            return
        path = d[0]
        dlg = UpdateProgressDialog(
            self, url=url, dest=path,
            sha1=asset.get('sha1'), size=asset.get('size'),
            title='下载 v%s · %s' % (info.get('latest', ''), default_name),
            concurrency=self.app.settings.get('concurrency', 16),
            segmented=self.app.settings.get('segmented', True),
            fallback=asset.get('fallback'))
        dlg.start()
        dlg.exec_()
        if getattr(dlg, '_ok', False):
            self.app.window.show_toast('已下载 %s' % default_name, 'success')

    # ---------- 一键更新（就地替换，无需重装）----------
    def do_inplace_update(self):
        """下载新版本到临时文件，交给内置更新助手（upset.exe）就地替换并重启。"""
        info = getattr(self, '_latest_info', None)
        if not info:
            return
        assets = getattr(self, '_pending_assets', None) or info.get('assets') or {}
        # 就地更新用「绿色版（单文件）」即可覆盖当前 exe；没有则退回安装包
        asset = assets.get('portable') or assets.get('setup') or {}
        url = asset.get('url')
        if not url:
            self.app.window.show_toast('版本信息中缺少下载地址', 'error')
            return
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        upset_path = os.path.join(exe_dir, 'upset.exe')
        if not os.path.isfile(upset_path):
            self.app.window.show_toast(
                '更新助手（upset.exe）缺失，请改用下方「下载绿色版手动更新」', 'error')
            self.dl_portable_btn.setVisible(True)
            return
        if not os.access(exe_dir, os.W_OK):
            self.app.window.show_toast(
                '当前目录不可写，无法就地更新，请改用下方「下载绿色版手动更新」',
                'error')
            self.dl_portable_btn.setVisible(True)
            return
        remote = info.get('latest') or info.get('version') or 'new'
        tmp = os.path.join(tempfile.gettempdir(), 'zmcl_update_%s.exe' % remote)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        dlg = UpdateProgressDialog(
            self, url=url, dest=tmp,
            sha1=asset.get('sha1'), size=asset.get('size'),
            title='下载更新 v%s' % remote,
            concurrency=self.app.settings.get('concurrency', 16),
            segmented=self.app.settings.get('segmented', True),
            fallback=asset.get('fallback'),
            complete_callback=self._after_update_download)
        dlg.start()
        dlg.exec_()

    def _after_update_download(self, dest):
        """下载完成后：启动更新助手替换并重启，随后退出当前进程。"""
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        upset_path = os.path.join(exe_dir, 'upset.exe')
        if not os.path.isfile(upset_path) or not os.path.isfile(dest):
            self.app.window.show_toast('更新文件缺失，更新中止', 'error')
            return
        self.app.window.show_toast('正在更新并重启…', 'info')
        try:
            from PyQt5.QtCore import QProcess
            ok = QProcess.startDetached(
                upset_path, [sys.executable, dest, str(os.getpid())])
            if not ok:
                self.app.window.show_toast('无法启动更新助手，请手动更新', 'error')
                return
            # 退出当前启动器，交给 upset 替换并重启
            app = QApplication.instance()
            if app:
                app.quit()
            else:
                sys.exit(0)
        except Exception as e:
            self.app.window.show_toast('更新启动失败：%s' % e, 'error')

    def save(self):
        s = self.app.settings
        s['javaPath'] = self.java_edit.text() or 'java'
        s['minMemory'] = self.min_spin.value()
        s['maxMemory'] = self.max_spin.value()
        s['downloadSource'] = self.source_map.get(self.source_combo.currentText(), 'bmclapi')
        custom_url = self.custom_edit.text().strip()
        if s['downloadSource'] == 'custom' and not custom_url:
            # 选了自定义却没填地址：退回到 BMCLAPI 并提示，避免下载退化成官方源还不自知
            s['downloadSource'] = 'bmclapi'
            custom_url = ''
            self.app.window.show_toast('自定义镜像地址为空，已改用 BMCLAPI', 'info')
        s['customSourceUrl'] = custom_url
        try:
            from core.config import set_custom_base
            set_custom_base(custom_url)
        except Exception:
            pass
        s['theme'] = self.theme_combo.currentData() or 'light'
        s['concurrency'] = self.conc_spin.value()
        s['segmented'] = self.seg_check.isChecked()
        s['showStagePanel'] = self.stage_check.isChecked()
        s['skipOnboarding'] = self.onboard_check.isChecked()
        s['notifySound'] = self.notify_sound_check.isChecked()
        s['notifyToast'] = self.notify_toast_check.isChecked()
        s['elastic'] = self.elastic_check.isChecked()
        s['gameLang'] = self.lang_map.get(self.lang_combo.currentText(), 'zh_cn')
        mode = self.proxy_combo.currentIndex()
        s['proxyMode'] = ['system', 'none', 'custom'][mode]
        s['proxyUrl'] = self.proxy_edit.text().strip()
        s['msaClientId'] = self.msa_edit.text().strip()
        s['yggServer'] = self.ygg_edit.text().strip()
        self.app.save_settings()
        # 立即应用代理设置
        try:
            from core.http import set_proxy
            if s['proxyMode'] == 'none':
                set_proxy('')
            elif s['proxyMode'] == 'custom' and s['proxyUrl']:
                set_proxy(s['proxyUrl'])
            else:
                set_proxy(None)
        except Exception:
            pass
        # 换了镜像源就重置熔断状态，让新源重新被评估
        try:
            from core.http import reset_circuit
            reset_circuit()
        except Exception:
            pass
