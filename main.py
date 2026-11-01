import os
import sys
import faulthandler
import traceback
import warnings

warnings.filterwarnings('ignore', message='.*character detection dependency.*')


def resource_path(rel):
    """兼容 PyInstaller 打包：打包后用 _MEIPASS，开发时回退到源码目录。"""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# 崩溃日志：即使程序闪退/段错误，也能把栈写进文件，方便定位
HERE = os.path.dirname(os.path.abspath(__file__))
CRASH_LOG = os.path.join(HERE, '_crash.log')
_CLOG = None
try:
    _CLOG = open(CRASH_LOG, 'a', encoding='utf-8')
    faulthandler.enable(_CLOG)  # 段错误也写进崩溃日志文件
except Exception:
    if sys.stderr is not None:
        try:
            faulthandler.enable()
        except Exception:
            pass
# PyInstaller --windowed 下没有控制台，sys.stderr 为 None，此时不能调用会写 stderr 的接口
if sys.stderr is not None:
    try:
        faulthandler.dump_traceback_later(30, exit=False)  # 卡死超 30s 也 dump 一次
    except Exception:
        pass


def _excepthook(t, v, tb):
    msg = ''.join(traceback.format_exception(t, v, tb))
    try:
        with open(CRASH_LOG, 'w', encoding='utf-8') as f:
            f.write(msg)
    except Exception:
        pass
    err = sys.__stderr__
    if err is not None:
        try:
            err.write(msg + '\n')
        except Exception:
            pass


sys.excepthook = _excepthook

sys.path.insert(0, HERE)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from app import AppController


def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 设置启动器图标（窗口/任务栏），避免默认丑图标
    icon_path = resource_path('icon.png')
    if os.path.exists(icon_path):
        try:
            from PyQt5.QtGui import QIcon
            app.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass
    ctrl = AppController()
    ctrl.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    try:
        main()
    except Exception:
        _excepthook(*sys.exc_info())
        raise
