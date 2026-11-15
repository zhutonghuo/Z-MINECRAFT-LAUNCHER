# -*- coding: utf-8 -*-
"""检查更新 + 内置下载安装包。

- fetch_version_info(): 拉取官网 version.json。
- UpdateProgressDialog: 用启动器内置的 download_file 下载安装包，
  带进度条 / 速度 / 完成提示，下载前由调用方用 QFileDialog 问好存放位置。
"""
import os

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QProgressBar,
                             QPushButton, QDialogButtonBox, QMessageBox)
from PyQt5.QtCore import Qt, QDateTime, QUrl
from PyQt5.QtGui import QDesktopServices

from core.http import get_with_retry, friendly_error
from core.appinfo import VERSION_INFO_URL


def fetch_version_info():
    """拉取服务器版本信息 JSON；失败抛出中文友好异常。"""
    try:
        r = get_with_retry(VERSION_INFO_URL, tries=4, timeout=20)
        return r.json()
    except Exception as e:
        raise Exception(friendly_error(e))


class UpdateProgressDialog(QDialog):
    """下载单个安装包文件的进度弹窗。

    url/dest/sha1/size 来自 version.json 的 assets；
    on_delta 走 Bridge 把增量字节从下载线程抛回主线程累加。
    """

    def __init__(self, parent, url, dest, sha1=None, size=None, title='下载更新',
                 concurrency=16, segmented=True, fallback=None,
                 complete_callback=None):
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self.sha1 = sha1
        self.size = size
        self.fallback = fallback
        self.complete_callback = complete_callback
        self._job_concurrency = concurrency
        self._job_segmented = segmented
        self._done = 0
        self._samples = []
        self._finished = False
        self._ok = None

        self.setWindowTitle(title)
        self.setMinimumWidth(480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        layout = QVBoxLayout(self)

        self.lbl = QLabel('准备下载...')
        self.lbl.setWordWrap(True)
        layout.addWidget(self.lbl)

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000 if size else 0)
        layout.addWidget(self.bar)

        self.sub = QLabel('')
        layout.addWidget(self.sub)

        self.btn_open = QPushButton('打开所在文件夹')
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_close = QPushButton('关闭')
        self.btn_close.setEnabled(False)
        self.btn_close.clicked.connect(self.accept)

        box = QDialogButtonBox()
        box.addButton(self.btn_open, QDialogButtonBox.ActionRole)
        box.addButton(self.btn_close, QDialogButtonBox.RejectRole)
        layout.addWidget(box)

        # 跨线程把增量字节抛回主线程
        from ui.worker import Worker, Bridge
        self.bridge = Bridge()
        self.bridge.report.connect(self._on_report)
        self.worker = Worker(self._job)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        # 强引用，避免 QThread 被 GC 回收导致闪退
        self._worker = self.worker

    def start(self):
        self.worker.start()

    # ---- 下载线程 ----
    def _job(self):
        from core.download import (download_file, set_connection_limit,
                                   set_segmented)
        set_connection_limit(self._job_concurrency)
        set_segmented(self._job_segmented)
        ok = download_file(
            self.url, self.dest, sha1=self.sha1, size=self.size,
            on_delta=lambda n: self.bridge.report.emit(('delta', n)),
            name=os.path.basename(self.dest), fallback=self.fallback)
        return ok

    # ---- 主线程槽 ----
    def _on_report(self, payload):
        if self._finished or payload[0] != 'delta':
            return
        n = payload[1]
        self._done += n
        now = QDateTime.currentMSecsSinceEpoch() / 1000.0
        self._samples.append((now, self._done))
        while len(self._samples) > 2 and now - self._samples[0][0] > 2.0:
            self._samples.pop(0)
        total = self.size or 0
        if total:
            pct = min(100.0, 100.0 * self._done / total)
            self.bar.setValue(int(pct * 10))
        else:
            self.bar.setRange(0, 0)
        speed = 0.0
        if len(self._samples) >= 2:
            t0, d0 = self._samples[0]
            dt = now - t0
            if dt > 0.3:
                speed = (self._done - d0) / dt
        done_mb = self._done / 1048576.0
        total_mb = (total / 1048576.0) if total else 0.0
        txt = '%.1f / %.1f MB' % (done_mb, total_mb) if total else '%.1f MB' % done_mb
        if speed > 0:
            txt += '　·　%.1f MB/s' % (speed / 1048576.0)
        self.sub.setText(txt)

    def _on_done(self, ok):
        self._finished = True
        self._ok = ok
        self.bar.setRange(0, 1000)
        self.bar.setValue(1000)
        if ok:
            # 完成提醒：播放提示音 + 发系统通知
            try:
                from core.notify import notify_complete
                app = getattr(self, 'app', None)
                if app is None:
                    p = self.parent()
                    app = getattr(p, 'app', None)
                settings = getattr(app, 'settings', None) if app else None
                notify_complete('ZMCLauncher', '新版本下载完成', settings, app)
            except Exception:
                pass
            # 若是「一键更新」流程：下载完成即交给回调处理（就地替换并重启），
            # 不再展示「打开文件夹」之类的按钮。
            if self.complete_callback:
                try:
                    self.complete_callback(self.dest)
                except Exception as e:
                    print('complete_callback 出错:', e)
                self.accept()
                return
            self.lbl.setText('下载完成！\n已保存到：\n%s' % self.dest)
            self.sub.setText('')
            self.btn_open.setEnabled(True)
            self.btn_close.setText('完成')
            self.btn_close.setEnabled(True)
        else:
            from core.download import last_error
            err = last_error()
            msg = friendly_error(err) if err else '下载未完成'
            self.lbl.setText('下载失败：%s' % msg)
            self.sub.setText('请检查网络连接后重试。')
            self.btn_close.setText('关闭')
            self.btn_close.setEnabled(True)

    def _on_error(self, err):
        self._finished = True
        self._ok = False
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.lbl.setText('下载出错：%s' % err)
        self.sub.setText('')
        self.btn_close.setText('关闭')
        self.btn_close.setEnabled(True)

    def _open_folder(self):
        try:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.dirname(os.path.abspath(self.dest))))
        except Exception:
            pass
