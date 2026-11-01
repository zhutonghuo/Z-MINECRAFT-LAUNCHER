import os
import datetime

from PyQt5.QtWidgets import QApplication

from core.config import load_settings, save_settings, resolve_data_dir, write_saved_data_dir, read_saved_data_dir
from core.auth import list_accounts
from core.version import merge_version, build_command
from core.java import detect_java_runtimes, pick_java
from core.launcher import launch
from ui.main_window import MainWindow
from ui.console_dialog import ConsoleDialog
from ui.worker import Worker
from ui.styles import get_stylesheet


class AppController:
    def __init__(self):
        # 1) 先确定数据目录：首次弹窗让用户选；之后每次检查目录是否还在
        data_root = self._resolve_data_dir()
        # 2) 加载该目录下的设置（dataRoot 以用户选择为准）
        self.settings = load_settings(data_root)
        self.data_root = self.settings['dataRoot']
        self.accounts = []
        self.current_account = None
        self.apply_proxy()
        self.window = MainWindow(self)
        self.apply_theme()
        self.refresh_accounts()

    def _resolve_data_dir(self):
        """确定数据目录：已记录且仍存在 → 直接用；否则弹向导让用户选。"""
        # 弹窗前先套一层默认深色样式，保证向导对话框也好看
        app = QApplication.instance()
        if app and not app.styleSheet():
            from ui.styles import get_stylesheet
            app.setStyleSheet(get_stylesheet('dark'))

        existing = resolve_data_dir()
        if existing is not None:
            return existing

        # 首次或未找到（如 U 盘拔出）：弹向导。suggest 用上次选过的位置（即便已丢失）
        from ui.data_dir_dialog import DataDirDialog
        last = read_saved_data_dir()
        dlg = DataDirDialog(suggest=last, lost=bool(last))
        dlg.exec_()
        chosen = dlg.chosen_path
        if chosen:
            write_saved_data_dir(chosen)
        return chosen

    def apply_proxy(self):
        """应用网络代理设置"""
        try:
            from core.http import set_proxy
            mode = self.settings.get('proxyMode', 'system')
            if mode == 'none':
                set_proxy('')
            elif mode == 'custom' and self.settings.get('proxyUrl'):
                set_proxy(self.settings['proxyUrl'])
            else:
                set_proxy(None)
        except Exception:
            pass

    def apply_theme(self):
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_stylesheet(self.settings.get('theme', 'dark')))

    def set_theme(self, theme):
        self.settings['theme'] = theme
        save_settings(self.settings)
        self.apply_theme()

    def get_settings(self):
        return self.settings

    def save_settings(self):
        save_settings(self.settings)

    def refresh_accounts(self):
        self.accounts = list_accounts(self.data_root)
        last = self.settings.get('lastAccount')
        self.current_account = None
        for a in self.accounts:
            if a.get('uuid') == last:
                self.current_account = a
                break
        if not self.current_account and self.accounts:
            self.current_account = self.accounts[0]
        self.window.update_account_label()

    def set_current_account(self, acc):
        self.current_account = acc
        self.settings['lastAccount'] = acc.get('uuid')
        save_settings(self.settings)
        self.window.update_account_label()

    def refresh_account(self, acc=None):
        """刷新账号令牌与角色资料（后台线程），完成回调 on_done"""
        from core.account import refresh_account as _refresh
        from core.auth import save_account
        from ui.worker import Worker
        target = acc or self.current_account
        if not target:
            raise Exception('请先登录账号')
        if target.get('type') == 'offline':
            raise Exception('离线账号无需刷新')

        def job():
            return _refresh(target, self.settings.get('msaClientId') or None)

        def on_done(new_acc):
            save_account(self.data_root, new_acc)
            self.refresh_accounts()

        w = Worker(job)
        w.done.connect(on_done)
        w.finished.connect(w.deleteLater)
        self._acc_refresh_worker = w
        w.start()
        return w

    def launch_instance(self, instance):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = os.path.join(self.data_root, 'logs', 'game_%s.log' % ts)
        dlg = ConsoleDialog(log_path=log_path,
                             show_stage=self.settings.get('showStagePanel', True))
        self._console_dlg = dlg  # 持有引用，避免被 GC 回收导致控制台一闪关闭
        dlg.show()
        acc = self.current_account

        def job():
            from core import mc_log
            from core.account import refresh_account, account_expired
            from core.auth import save_account

            if not acc:
                raise Exception('请先登录账号')
            dlg.stage_begin.emit('正在准备启动环境（读取账号 / 版本信息）')
            dlg.log.emit(mc_log.stage('正在初始化启动环境...'))
            dlg.log.emit(mc_log.stage('使用账号：' + mc_log.account_desc(acc)))

            # 正版微软账号：令牌约 24 小时过期，过期后游戏会判定未验证、
            # 直接掉进“试玩/购买”界面。这里在启动前自动刷新，避免进试玩。
            if acc.get('type') == 'microsoft' and account_expired(acc):
                dlg.log.emit(mc_log.stage('正版令牌可能已过期，正在自动刷新...'))
                try:
                    new_acc = refresh_account(acc, self.settings.get('msaClientId') or None)
                    save_account(self.data_root, new_acc)
                    acc = new_acc
                    self.current_account = new_acc
                    dlg.log.emit(mc_log.stage('令牌刷新成功，账号：' + new_acc.get('name', '')))
                except Exception as e:
                    dlg.log.emit(mc_log.stage('⚠ 令牌刷新失败，将尝试用旧令牌启动：' + str(e)
                                             + '（若进入试玩界面，请点侧栏“刷新”后重试）'))
            elif acc.get('type') == 'microsoft':
                dlg.log.emit(mc_log.stage('正版令牌仍在有效期内，直接启动'))

            merged = merge_version(self.data_root, instance['versionId'])
            if not merged:
                raise Exception('版本未安装: ' + instance['versionId'])
            java_path = instance.get('javaPath') or self.settings.get('javaPath') or 'java'
            if java_path in (None, 'java', ''):
                runtimes = detect_java_runtimes()
                java_path = pick_java(runtimes) or 'java'

            dlg.log.emit(mc_log.stage('Java 路径：' + java_path))
            dlg.log.emit(mc_log.stage('内存设置：最大 %d MB / 最小 %d MB'
                                     % (self.settings.get('maxMemory', 2048),
                                        self.settings.get('minMemory', 512))))
            dlg.log.emit(mc_log.stage('游戏版本：' + instance['versionId']))

            cmd, nd = build_command(self.data_root, merged, acc, instance, java_path, self.settings)
            dlg.log.emit(mc_log.stage('已拼接启动命令，开始启动游戏进程...'))
            dlg.log.emit(mc_log.stage('日志文件已保存：' + log_path))
            dlg.log.emit(mc_log.stage('提示：Java 接管道时可能攒批输出，若下方短暂空白属正常，'
                                     '游戏仍在运行；上方「启动进度台」会实时显示当前步骤与耗时。'))
            dlg.stage_set.emit('正在启动 Java 虚拟机...', 5)

            def cb(line):
                dlg.log.emit(line)            # 原文保留，便于排错
                zh = mc_log.humanize(line)    # 顺手给出一句中文说明
                if zh:
                    dlg.log.emit('   ↳ ' + zh)
                st = mc_log.log_stage(line)   # 命中关键步骤则推进进度台
                if st:
                    dlg.stage_set.emit(st[0], st[1])

            rc = launch(cmd, instance['gameDir'], log_cb=cb, log_path=log_path)
            dlg.stage_finish.emit('游戏进程已退出（退出码 %s，0 = 正常关闭）' % rc, 100)
            dlg.log.emit(mc_log.stage('游戏进程已退出，退出码 %s（0 = 正常关闭）' % rc))
            return acc

        w = Worker(job)
        w.done.connect(lambda r: self.refresh_accounts())
        w.error.connect(self._on_launch_error)
        w.finished.connect(w.deleteLater)
        self._launch_worker = w
        w.start()

    def _on_launch_error(self, e):
        dlg = getattr(self, '_console_dlg', None)
        if dlg is not None:
            try:
                dlg.stage_finish.emit('❌ 启动失败：' + e, 100)
            except Exception:
                pass
            try:
                dlg.log.emit('❌ 启动失败：' + e)
            except Exception:
                pass

    def show(self):
        self.window.show()
