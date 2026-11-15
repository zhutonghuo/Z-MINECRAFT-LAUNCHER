from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QPropertyAnimation, QTimer


class Toast(QWidget):
    def __init__(self, parent, text, kind='success', timeout=3200):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setObjectName('Toast')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(10)
        icon = QLabel({'success': '✔', 'error': '✕'}.get(kind, 'ℹ'))
        icon.setObjectName('ToastIcon')
        label = QLabel(text)
        label.setObjectName('ToastText')
        layout.addWidget(icon)
        layout.addWidget(label)
        self._timeout = timeout
        color = {'success': '#2e9e4f', 'error': '#d1453b'}.get(kind, '#2f7fd6')
        self.setStyleSheet(
            "Toast{background:%s;border-radius:12px;}"
            "ToastText{color:#ffffff;font-size:13px;font-weight:600;}"
            "ToastIcon{color:#ffffff;font-size:16px;}" % color)
        self.adjustSize()

    def showEvent(self, e):
        super().showEvent(e)
        self._fade(0.0, 1.0, 250)
        QTimer.singleShot(self._timeout, self._hide)

    def _fade(self, s, e, ms):
        self.setWindowOpacity(s)
        a = QPropertyAnimation(self, b'windowOpacity')
        a.setDuration(ms)
        a.setStartValue(s)
        a.setEndValue(e)
        a.start()
        self._anim = a

    def _hide(self):
        a = QPropertyAnimation(self, b'windowOpacity')
        a.setDuration(300)
        a.setStartValue(1.0)
        a.setEndValue(0.0)
        a.finished.connect(self.close)
        a.start()
        self._anim = a
