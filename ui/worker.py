from PyQt5.QtCore import QThread, QObject, pyqtSignal

# 正在运行 / 尚未回收的 Worker 全局登记表。
# QThread 一旦在运行中被 Python GC 回收，Qt 会直接 abort() 整个进程（表现为
# 无任何报错的闪退）。因此必须由这里强引用住每个 Worker，直到它真正结束。
_ACTIVE_WORKERS = set()


class Bridge(QObject):
    report = pyqtSignal(object)


class Worker(QThread):
    progress = pyqtSignal(int, int)
    item = pyqtSignal(int, int, object, bool)
    log = pyqtSignal(str)
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        _ACTIVE_WORKERS.add(self)
        self.finished.connect(self._release)

    def _release(self):
        # 线程已结束，从全局登记表移除，让 Python 回收它
        _ACTIVE_WORKERS.discard(self)

    def run(self):
        try:
            res = self.fn()
            self.done.emit(res)
        except Exception as e:
            self.error.emit(str(e))
