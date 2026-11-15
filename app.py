import os
import datetime
import shutil

from PyQt5.QtWidgets import QApplication

from core.config import (load_settings, save_settings, resolve_data_dir,
                         write_saved_data_dir, read_saved_data_dir,
                         ensure_data_root)
from core.auth import list_accounts
from core.version import merge_version, build_command, missing_language_assets
from core.java import detect_java_runtimes, pick_java
from core.launcher import launch
from ui.main_window import MainWindow
from ui.console_dialog import ConsoleDialog
from ui.worker import Worker
from ui.styles import get_stylesheet
from ui.elastic import ElasticFilter, set_elastic


class AppController:
    def __init__(self):
        # 自动沿用其它版本启动器留下的数据目录时记录下来（设置页会提示）
        self.auto_adopted_data_dir = None
        # 本次数据目录是如何确定的：located / discovered / first_time / relocated
        self.data_dir_source = None
        # 清理上一次「一键更新」就地替换遗留的备份 exe（<exe>.old）
        try:
            old = os.path.abspath(sys.executable) + '.old'
            if os.path.isfile(old):
                os.remove(old)
        except Exception:
            pass
        # 1) 先确定数据目录：首次弹窗让用户选；之后每次检查目录是否还在
        data_root = self._resolve_data_dir()
        # 2) 加载该目录下的设置（dataRoot 以用户选择为准）
        self.settings = load_settings(data_root)
        self.data_root = self.settings['dataRoot']
        self.accounts = []
        self.current_account = None
        self.apply_proxy()
        self.window = MainWindow(self)
        set_elastic(self.settings.get('elastic', True))
        qapp = QApplication.instance()
        if qapp:
            self._elastic_filter = ElasticFilter()
            qapp.installEventFilter(self._elastic_filter)
        self.apply_theme()
        self.refresh_accounts()

    def _resolve_data_dir(self):
        """确定数据目录。

        优先级：
        1) 记忆文件里记录的目录还在 → 直接用（用户之前明确选过）。
        2) 扫描到本机已有「启动器可用文件」的目录（其它版本启动器用过的）
           → 自动沿用它，不再打扰用户弹向导。
        3) 都没有 → 弹向导让用户选。
        """
        # 弹窗前先套一层默认深色样式，保证向导对话框也好看
        app = QApplication.instance()
        if app and not app.styleSheet():
            from ui.styles import get_stylesheet
            app.setStyleSheet(get_stylesheet('dark'))

        existing = resolve_data_dir()
        if existing is not None:
            self.data_dir_source = 'located'
            return existing

        # 其它版本启动器（或本启动器换了位置）留下的数据目录：自动沿用
        found = self._auto_discover_data_dir()
        if found:
            write_saved_data_dir(found)
            self.auto_adopted_data_dir = found
            self.data_dir_source = 'discovered'
            return found

        # 首次或未找到（如 U 盘拔出）：弹向导。suggest 用上次选过的位置（即便已丢失）
        from ui.data_dir_dialog import DataDirDialog
        last = read_saved_data_dir()
        dlg = DataDirDialog(suggest=last, lost=bool(last))
        dlg.exec_()
        chosen = dlg.chosen_path
        if chosen:
            write_saved_data_dir(chosen)
        self.data_dir_source = 'relocated' if last else 'first_time'
        return chosen

    def _auto_discover_data_dir(self):
        """扫描本机，找出已有的启动器数据目录并自动沿用。

        只认「本启动器自己的」目录（有 launcher-config.json 或
        instances/*/instance.json），并且里面确有可用数据
        （版本/库/资源/账号），空目录一律不认。
        官方启动器、PCL、HMCL 等别的启动器的目录账号格式不同，
        混用会出乱子，只在设置页作为可选目标提示，由用户自己决定。
        这里走快速通道（常见位置 + 全局登记表），保证启动不被拖慢；
        深度扫描放到设置页后台执行。
        """
        try:
            from core.config import quick_find_data_dirs
            cands = [c for c in quick_find_data_dirs() if c.get('own')]
        except Exception:
            return None
        if not cands:
            return None
        return cands[0]['path']

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

    def migrate_data_dir(self, new_root):
        """把当前数据目录的全部内容移动到新位置（自动迁移）。

        只做文件移动与状态更新，不触碰任何 UI；UI 刷新请放在调用方的
        完成回调里（迁移在后台线程执行，避免大目录卡界面）。
        返回新目录的绝对路径。
        """
        old = self.data_root
        new = os.path.abspath(new_root)
        if new == os.path.abspath(old):
            return new
        os.makedirs(new, exist_ok=True)
        ensure_data_root(new)
        # 逐条移动：同盘是瞬间 rename，跨盘是 copy+删源，都不留残留
        for name in os.listdir(old):
            src = os.path.join(old, name)
            dst = os.path.join(new, name)
            if os.path.exists(dst):
                # 目标已存在（如 ensure_data_root 预建的空子目录）→ 目录则合并，文件则跳过
                if os.path.isdir(src) and os.path.isdir(dst):
                    _merge_move_dir(src, dst)
                continue
            shutil.move(src, dst)
        self.data_root = new
        self.settings['dataRoot'] = new
        write_saved_data_dir(new)
        save_settings(self.settings)
        return new


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

    def refresh_instances_page(self):
        """安装加载器后刷新「实例」页（重新读取实例列表）。"""
        for p in getattr(getattr(self, 'window', None), 'pages', []) or []:
            if hasattr(p, 'refresh'):
                try:
                    p.refresh()
                except Exception:
                    pass

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
            from core.account import token_valid
            new_acc = _refresh(target, self.settings.get('msaClientId') or None)
            # 刷新后校验令牌确实可用，避免“刷新成功但依旧未授权”的假象
            if not token_valid(new_acc):
                raise Exception('刷新完成，但新令牌仍无法通过官方校验，'
                                '请检查账号是否已购买 Minecraft Java 版或重新登录。')
            return new_acc

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

        # 在主线程就把账号快照下来：点“启动”这一刻用哪个账号就是哪个，
        # 之后即使后台线程再改 current_account 也不会影响本次启动。
        launch_acc = self.current_account

        def job():
            from core import mc_log
            from core.auth import save_account

            acc = launch_acc
            if not acc:
                raise Exception('请先登录账号')
            dlg.stage_begin.emit('正在准备启动环境（读取账号 / 版本信息）')
            dlg.log.emit(mc_log.stage('正在初始化启动环境...'))
            dlg.log.emit(mc_log.stage('使用账号：' + mc_log.account_desc(acc)))
            dlg.log.emit(mc_log.stage('★ 本次启动使用的账号是「%s」' % (acc.get('name') or '未知')))
            hint = mc_log.auth_hint(acc)
            if hint:
                dlg.log.emit(mc_log.stage('授权方式：' + hint))

            # 正版/第三方账号：启动前确认令牌可用。
            # 令牌失效时游戏会判定未授权而落到“试玩”界面，所以宁可在这里
            # 明确报错，也不要拿一个坏令牌去启动、让用户一头雾水。
            if acc.get('type') in ('microsoft', 'yggdrasil'):
                from core.account import ensure_fresh
                dlg.log.emit(mc_log.stage('正在校验账号令牌...'))
                ok, new_acc, msg = ensure_fresh(acc, self.settings.get('msaClientId') or None)
                dlg.log.emit(mc_log.stage('账号校验：' + (msg or '完成')))
                if not ok:
                    raise Exception('账号令牌不可用：' + msg +
                                    '\n请在左侧「账号」里重新登录该账号后再启动游戏。')
                if new_acc is not None and new_acc is not acc:
                    save_account(self.data_root, new_acc)
                    acc = new_acc
                    self.current_account = new_acc

            merged = merge_version(self.data_root, instance['versionId'])
            if not merged:
                raise Exception('版本未安装: ' + instance['versionId'])
            java_path = instance.get('javaPath') or self.settings.get('javaPath') or 'java'
            if java_path in (None, 'java', ''):
                runtimes = detect_java_runtimes()
                # 按版本要求选 Java（如 26.x 需要 25），避免用错版本导致启动失败
                want = (merged.get('javaVersion') or {}).get('majorVersion')
                java_path = pick_java(runtimes, want) or 'java'
                if want:
                    dlg.log.emit(mc_log.stage('该版本需要 Java %d，已选用：%s'
                                             % (want, java_path)))

            dlg.log.emit(mc_log.stage('Java 路径：' + java_path))
            dlg.log.emit(mc_log.stage('内存设置：最大 %d MB / 最小 %d MB'
                                     % (self.settings.get('maxMemory', 2048),
                                        self.settings.get('minMemory', 512))))
            dlg.log.emit(mc_log.stage('游戏版本：' + instance['versionId']))

            # 新实例首次启动会弹「Welcome to Minecraft!」引导页（不是试玩版），
            # 且默认是英文界面。这里预置实例配置：中文（简体）+ 跳过引导页。
            from core.version import apply_instance_options
            game_lang = self.settings.get('gameLang', 'zh_cn')
            changed = apply_instance_options(
                instance.get('gameDir'),
                lang=game_lang,
                skip_onboard=self.settings.get('skipOnboarding', True))
            if changed:
                dlg.log.emit(mc_log.stage('已预置实例配置：' + '、'.join(changed)))
            if game_lang and game_lang != 'en_us':
                missing = missing_language_assets(self.data_root, merged, game_lang)
                if missing:
                    dlg.log.emit(mc_log.stage(
                        '⚠ 缺少 %s 语言资源（%d 个文件），游戏可能回退为英文。'
                        '请到「版本」页重新安装该版本以补全资源。' % (game_lang, len(missing))))

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
        # 进入时明确告知用户数据文件夹的位置（不搞黑箱）
        src = getattr(self, 'data_dir_source', None)
        if src == 'discovered':
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(600, lambda: self._toast_auto_adopted(
                self.auto_adopted_data_dir))
        elif src == 'located':
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(600, lambda: self._toast_locate(
                self.data_root, '已定位到您的数据文件夹'))
        elif src in ('first_time', 'relocated'):
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(600, lambda: self._toast_locate(
                self.data_root,
                '已为您创建数据文件夹' if src == 'first_time'
                else '已切换到数据文件夹'))

    def _toast_auto_adopted(self, path):
        try:
            self.window.show_toast(
                '已自动沿用原启动器数据文件夹：' + path, 'info')
        except Exception:
            pass

    def _toast_locate(self, path, prefix):
        try:
            self.window.show_toast('%s：%s' % (prefix, path), 'info')
        except Exception:
            pass

def _merge_move_dir(src, dst):
    """把 src 目录内容合并移动到已存在的 dst（同名文件保留 dst，不覆盖）。"""
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s) and os.path.isdir(d):
            _merge_move_dir(s, d)
        elif os.path.exists(d):
            continue
        else:
            shutil.move(s, d)
    try:
        os.rmdir(src)
    except OSError:
        pass

