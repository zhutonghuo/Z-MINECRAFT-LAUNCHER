import os

from PyQt5.QtCore import pyqtSignal, QUrl, QTimer
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QTextEdit, QLabel, QPushButton,
                             QHBoxLayout, QProgressBar, QWidget)


class ConsoleDialog(QDialog):
    log = pyqtSignal(str)
    # 启动进度台信号（全部走排队连接，子线程发、主线程收，避免跨线程操作控件）
    stage_begin = pyqtSignal(str)        # 开始：显示第一步文字
    stage_set = pyqtSignal(str, int)     # 更新：文字 + 百分比
    stage_finish = pyqtSignal(str, int)  # 结束：文字 + 百分比

    def __init__(self, parent=None, log_path=None, show_stage=True):
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle('游戏控制台')
        self.setMinimumSize(760, 520)
        self.setObjectName('Page')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        self.title = QLabel('启动日志')
        self.title.setObjectName('PageTitle')
        layout.addWidget(self.title)

        # ---- 启动进度台 ----
        self.stage_panel = QWidget()
        self.stage_panel.setObjectName('StagePanel')
        sp_layout = QVBoxLayout(self.stage_panel)
        sp_layout.setContentsMargins(12, 10, 12, 10)
        sp_layout.setSpacing(8)
        top_row = QHBoxLayout()
        self.stage_title = QLabel('准备启动')
        self.stage_title.setObjectName('StageTitle')
        self.stage_time = QLabel('已运行 00:00')
        self.stage_time.setObjectName('StageTime')
        top_row.addWidget(self.stage_title)
        top_row.addStretch(1)
        top_row.addWidget(self.stage_time)
        sp_layout.addLayout(top_row)
        self.stage_bar = QProgressBar()
        self.stage_bar.setObjectName('StageBar')
        self.stage_bar.setRange(0, 100)
        self.stage_bar.setValue(0)
        self.stage_bar.setTextVisible(True)
        sp_layout.addWidget(self.stage_bar)
        self.stage_panel.setVisible(show_stage)
        layout.addWidget(self.stage_panel)

        self.text = QTextEdit()
        self.text.setObjectName('ConsoleText')
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.text, 1)
        bar = QHBoxLayout()
        bar.addStretch(1)
        if self.log_path:
            self.open_btn = QPushButton('打开日志文件')
            self.open_btn.setObjectName('ThemeButton')
            self.open_btn.clicked.connect(self.open_log)
            bar.addWidget(self.open_btn)
        self.copy_btn = QPushButton('清空')
        self.copy_btn.setObjectName('ThemeButton')
        self.copy_btn.clicked.connect(self.text.clear)
        bar.addWidget(self.copy_btn)
        layout.addLayout(bar)

        # 心跳计时器：即便游戏一条日志都不来，也实时显示耗时与进度，证明进程活着
        self._elapsed = 0.0
        self._max_auto = 92      # 时间推进上限（不到这个百分比不出强制 100%）
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)

        self.log.connect(self.append)
        self.stage_begin.connect(self.start_stage)
        self.stage_set.connect(self.set_stage)
        self.stage_finish.connect(self.stop_stage)

    # ---- 启动进度台 API ----
    def start_stage(self, text):
        self._elapsed = 0.0
        self.set_stage(text, 0)
        if not self._timer.isActive():
            self._timer.start()

    def set_stage(self, text, pct=None):
        if text is not None:
            self.stage_title.setText(text)
        if pct is not None:
            self.stage_bar.setValue(max(self.stage_bar.value(), int(pct)))

    def stop_stage(self, text, pct=100):
        if self._timer.isActive():
            self._timer.stop()
        self.stage_title.setText(text)
        self.stage_bar.setValue(int(pct))
        self.stage_time.setText('已运行 ' + self._fmt(self._elapsed))

    def _tick(self):
        self._elapsed += 0.5
        self.stage_time.setText('已运行 ' + self._fmt(self._elapsed))
        cur = self.stage_bar.value()
        if cur < self._max_auto:
            # 越接近上限推进越慢，给用户“一直在动”的反馈而不至于虚高
            step = max(1, int((self._max_auto - cur) / 28))
            self.stage_bar.setValue(min(self._max_auto, cur + step))

    @staticmethod
    def _fmt(sec):
        m = int(sec) // 60
        s = int(sec) % 60
        return '%02d:%02d' % (m, s)

    def append(self, line):
        self.text.append(line)
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def open_log(self):
        if self.log_path and os.path.isfile(self.log_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.log_path))
