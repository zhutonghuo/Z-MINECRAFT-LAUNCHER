# -*- coding: utf-8 -*-
"""弹性动画（已弃用）。

旧实现使用 QGraphicsOpacityEffect 做淡入，在透明父窗口（WA_TranslucentBackground）
下会把页面渲染到一张被初始化为白色的离屏缓冲，导致切页后整片发白。
现改为空操作：页面切换的动画改由 main_window 用纯几何滑动实现，不再发白。
"""


def set_elastic(enabled):
    pass


def is_elastic():
    return False


def animate_page(page):
    pass


class ElasticFilter:
    def eventFilter(self, obj, event):
        return False
