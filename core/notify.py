# -*- coding: utf-8 -*-
"""完成提醒：播放提示音 + 发系统通知。

音频用 Windows 自带的 MCI 接口（winmm.dll）播放 mp3：
不依赖任何第三方库，也不给打包体积添负担（QtMultimedia 会被 PyInstaller
拉进好几个 DLL）。

注意：MCI 用 ANSI 打开文件，**中文路径会失败**（报 MCIERR_INVALID_FILE 277），
所以播放前必须复制到纯 ASCII 的临时路径。

通知走 Qt 的系统托盘通知（Windows 下就是原生 toast）。
两个开关分别由设置项 notifySound / notifyToast 控制。
"""
import os
import shutil
import sys
import tempfile
import threading
import time

# 内置提示音（打包时随 exe 一起带走，放在包根目录）
SOUND_NAME = 'notify.mp3'

# 系统通知的应用程序名（Windows 通知中心里显示）
APP_NAME = 'ZMCLauncher'

_MCI_OK = 0


def _resource_path(rel):
    """兼容 PyInstaller 打包：打包后用 _MEIPASS，开发时回退到源码目录。"""
    base = getattr(sys, '_MEIPASS', None)
    if not base:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _bundled_sound():
    """定位内置提示音；找不到返回 None。"""
    for rel in (SOUND_NAME, os.path.join('assets', SOUND_NAME)):
        p = _resource_path(rel)
        if os.path.isfile(p):
            return p
    return None


def _user_sound(settings):
    """取用户配置的提示音路径。

    用户没指定就用内置的；指定了但文件不存在则回退到内置的。
    """
    path = (settings or {}).get('notifySoundPath') or ''
    if path and os.path.isfile(path):
        return path
    return _bundled_sound()


# ---------------------------------------------------------------- 音频播放

def _mci_send(command):
    """调用 mciSendStringA，返回 (错误码, 输出)。"""
    import ctypes
    mci = ctypes.windll.winmm
    buf = ctypes.create_string_buffer(255)
    rc = mci.mciSendStringA(ctypes.c_char_p(command.encode('ascii', 'replace')),
                            buf, 255, 0)
    return rc, buf.value.decode('utf-8', 'replace')


def _ascii_temp_dir():
    """找一个纯 ASCII 的临时目录。

    tempfile.gettempdir() 在用户名含中文时可能返回中文路径（虽然这里拿到的是
    8.3 短路径，但并非所有机器都开启 8.3 短名），MCI 打不开就麻烦了。
    优先用系统根下的短路径，退回 Windows 临时目录。
    """
    import ctypes
    candidates = []
    try:
        buf = ctypes.create_unicode_buffer(260)
        windir = ctypes.windll.kernel32.GetWindowsDirectoryW(buf, 260)
        if winddir:
            candidates.append(os.path.join(buf.value, 'Temp'))
    except Exception:
        pass
    try:
        candidates.append(tempfile.gettempdir())
    except Exception:
        pass
    for d in candidates:
        try:
            if d and os.path.isdir(d) and d.isascii():
                return d
        except Exception:
            continue
    # 都不可用就退回 tempfile（可能是短路径）
    try:
        return tempfile.gettempdir()
    except Exception:
        return os.path.abspath(os.sep)


def _ascii_temp_copy(path):
    """把音频复制到纯 ASCII 临时路径，返回 (临时路径, 是否为副本)。

    MCI 打不开中文路径，必须先复制。返回 None 表示复制失败。
    """
    try:
        if path.isascii() and _is_ascii_dir(os.path.dirname(path)):
            return path, False
    except Exception:
        pass
    tmp = os.path.join(_ascii_temp_dir(), 'zmc_notify.mp3')
    # 目标可能被上一次播放占用，先删再拷
    for _ in range(3):
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            time.sleep(0.2)
    for attempt in range(3):
        try:
            shutil.copyfile(path, tmp)
            return tmp, True
        except Exception:
            time.sleep(0.3)
    return None, False


def _is_ascii_dir(d):
    try:
        return d.isascii()
    except Exception:
        return False


def play_sound(path, wait=False):
    """播放音频文件。返回 True 表示成功发起播放。

    用 MCI 的 mpegvideo 类型播 mp3；打不开就退回 wave 类型再试一次。
    固定别名，复用前先关掉上一次没关干净的设备，避免第二次播不出来。
    """
    if not path or not os.path.isfile(path):
        return False
    alias = _ALIAS
    # 上一次可能还开着（播完没关），先关掉再重开
    try:
        _mci_send('stop %s' % alias)
        _mci_send('close %s' % alias)
    except Exception:
        pass
    opened = False
    try:
        rc, _ = _mci_send('open "%s" type mpegvideo alias %s' % (path, alias))
        if rc == _MCI_OK:
            opened = True
        else:
            rc, _ = _mci_send('open "%s" type waveaudio alias %s' % (path, alias))
            if rc == _MCI_OK:
                opened = True
        if not opened:
            return False
        if wait:
            _mci_send('play %s wait' % alias)
            _mci_send('close %s' % alias)
        else:
            _mci_send('play %s' % alias)
        return True
    except Exception:
        return False


_ALIAS = 'zmc_nfy'


def _cleanup_temp(path):
    """删掉临时副本（播放结束后调用）。"""
    try:
        os.remove(path)
    except Exception:
        pass


def play_notify_sound(settings):
    """按设置播放提示音。notifySound 为 False 时不播。

    返回 True 表示已成功发起播放。
    """
    if not (settings or {}).get('notifySound', True):
        return False
    src = _user_sound(settings)
    if not src:
        return False
    path, is_copy = _ascii_temp_copy(src)
    if not path:
        return False
    ok = play_sound(path)
    if ok and is_copy:
        # 等播完再删临时文件（ MCI 播放期间文件被占用）
        _closer_when_done(path)
    return ok


def _closer_when_done(path):
    """后台等播放结束，关闭 MCI 设备并清理临时文件。"""
    def worker():
        try:
            for _ in range(400):          # 最多等 40 秒
                time.sleep(0.1)
                rc, state = _mci_send('status %s mode' % _ALIAS)
                if rc != _MCI_OK or state.strip().lower() == 'stopped':
                    break
            _mci_send('stop %s' % _ALIAS)
            _mci_send('close %s' % _ALIAS)
        except Exception:
            pass
        finally:
            _cleanup_temp(path)
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------- 系统通知

def send_system_notification(title, message, settings=None, app=None):
    """发系统通知（Windows 原生 toast）。返回 True 表示已发出。

    走 QSystemTrayIcon.showMessage——注意托盘图标必须先 show() 且带图标，
    否则 Windows 会静默忽略，通知根本不弹。
    """
    if settings is not None and not settings.get('notifyToast', True):
        return False
    try:
        from PyQt5.QtWidgets import QSystemTrayIcon, QApplication
        from PyQt5.QtGui import QIcon
        app = app or QApplication.instance()
        if app is None:
            return False
        tray = getattr(send_system_notification, '_tray', None)
        if tray is None:
            tray = QSystemTrayIcon()
            send_system_notification._tray = tray
        if not tray.isVisible():
            icon_path = _resource_path('icon.png')
            if os.path.isfile(icon_path):
                tray.setIcon(QIcon(icon_path))
            tray.show()
        tray.showMessage(title or APP_NAME, message or '',
                         QSystemTrayIcon.Information, 8000)
        return True
    except Exception:
        return False


def notify_complete(title, message, settings=None, app=None):
    """完成提醒：播放提示音 + 发系统通知。

    两个开关独立生效，任一关闭都不影响另一个。
    返回 (是否播了音, 是否发了通知)。
    """
    settings = settings or {}
    played = False
    notified = False
    try:
        played = play_notify_sound(settings)
    except Exception:
        played = False
    try:
        notified = send_system_notification(title, message, settings, app)
    except Exception:
        notified = False
    return played, notified
