# -*- coding: utf-8 -*-
"""启动器「说明书」页：左侧边栏导航进入，通俗讲清怎么用。

不堆术语，按「先看这个 → 三步上手 → 各功能 → 常见问题」组织，
每个小节是一张卡片，扫一眼就懂。
"""
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QScrollArea, QFrame)
from PyQt5.QtCore import Qt

from core.appinfo import LAUNCHER_VERSION


def _card(title, body_html, parent=None):
    """生成一张说明卡片：标题 + 可换行的富文本正文。"""
    c = QFrame(parent)
    c.setObjectName('Card')
    lay = QVBoxLayout(c)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(8)
    t = QLabel(title)
    t.setObjectName('CardTitle')
    lay.addWidget(t)
    b = QLabel(body_html)
    b.setObjectName('PageHint')
    b.setWordWrap(True)
    b.setTextFormat(Qt.RichText)
    b.setOpenExternalLinks(False)
    lay.addWidget(b)
    return c


class ManualPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setObjectName('Page')

        scroll = QScrollArea(self)
        scroll.setObjectName('Scroll')
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setObjectName('PageScroll')
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(16)

        title = QLabel('说明书')
        title.setObjectName('PageTitle')
        layout.addWidget(title)

        sub = QLabel('Z MINECRAFT LAUNCHER · 当前版本 v%s · 几分钟读完就能上手' % LAUNCHER_VERSION)
        sub.setObjectName('PageHint')
        layout.addWidget(sub)

        # ---- 这是什么 ----
        layout.addWidget(_card(
            '这是什么？',
            '一个轻量的 <b>Minecraft Java 版</b> 启动器：帮你管理账号、游戏版本、'
            '加载器和模组，点一下就能进游戏。<br>'
            '全程中文、无广告、不大，主打「少点几下」。'))

        # ---- 三步上手 ----
        layout.addWidget(_card(
            '三步上手（最快路线）',
            '1️⃣ <b>左侧「账号」→ 登录</b>：没有正版账号就选「离线账号」，填个名字即可玩。<br>'
            '2️⃣ <b>左侧「版本」→ 安装一个游戏版本</b>（比如 1.21.x），想要模组就顺手装个加载器（Fabric/Forge 等）。<br>'
            '3️⃣ <b>左侧「实例」→ 选中版本 → 启动</b>：第一次会让你选 Java，按提示选好即可开玩。'))

        # ---- 账号 ----
        layout.addWidget(_card(
            '添加账号',
            '• <b>正版微软</b>：点「登录」按流程授权，能进官方服务器、有皮肤。<br>'
            '• <b>离线账号</b>：自己起个名字就行，适合单人 / 进第三方服务器。<br>'
            '• <b>第三方登录</b>：先在「设置」填好验证服务器地址（如 littleskin），再用用户名密码登录。<br>'
            '侧边栏的账号列表点一下就能切换，不用反复登录。'))

        # ---- 版本 / 加载器 ----
        layout.addWidget(_card(
            '安装版本与加载器',
            '在「版本」页：<br>'
            '• 选一个游戏版本点 <b>安装</b>，内置镜像会自动下载（节点不稳会重试 / 切官方源）。<br>'
            '• 想要模组、光影：装好版本后选 <b>Fabric / Quilt / Forge / NeoForge / OptiFine</b> 等加载器，'
            '选版本即装即玩。<br>'
            '• 装完后回到「实例」就能看到对应实例。'))

        # ---- 模组 / 资源 ----
        layout.addWidget(_card(
            '加模组 / 资源包 / 光影 / 世界',
            '在「模组」页里，把文件 <b>直接拖进对应实例的卡片</b>，会自动归位：<br>'
            '• Mod 放 Mods、资源包放 resourcepacks、光影放 shaderpacks、世界放 saves。<br>'
            '• 也能在实例里逐个启用 / 禁用 / 删除，或导入 .mcworld 压缩包。'))

        # ---- 启动 ----
        layout.addWidget(_card(
            '启动游戏',
            '在「实例」页选中要玩的世界，点 <b>启动</b>。<br>'
            '若提示缺 Java：去「设置」点「自动检测」选一个，或手动填 Java 路径。<br>'
            '下方「启动进度台」会实时显示当前步骤与耗时，即使游戏日志暂时空白也能看到进度。'))

        # ---- 检查更新（新功能）----
        layout.addWidget(_card(
            '检查更新（新功能）',
            '去「设置」最上方点 <b>检查更新</b>：<br>'
            '• 自动拉取官网版本信息，和当前版本对比。<br>'
            '• 发现有新版本会列出更新内容，点 <b>下载新版安装包</b>（或绿色版）。<br>'
            '• 会先让你选把安装包保存到哪（默认下载文件夹），然后用启动器内置下载功能拉取，'
            '带进度条；下完可直接「打开所在文件夹」运行。'))

        # ---- 常见问题 ----
        layout.addWidget(_card(
            '常见问题',
            '❓ <b>启动报「找不到 Java」</b>：设置里「自动检测」一下，或去装个 Java 并填路径。<br>'
            '❓ <b>下载很慢 / 卡住</b>：多是镜像节点抽风，启动器会自动重试并降级到官方源；'
            '也可在「设置」切换下载镜像源或调并发数。<br>'
            '❓ <b>进游戏变成英文</b>：实例缺少中文语言包，到「版本」页重装该版本即可补全。<br>'
            '❓ <b>账号列表空白</b>：刷新或重新登录即可恢复。'))

        # ---- 数据存放 ----
        layout.addWidget(_card(
            '我的数据存在哪？',
            '账号、游戏版本、库、资源、日志等都放在「启动器数据文件夹」里'
            '（在「设置」可查看 / 迁移位置）。<br>'
            '换电脑时可整体搬走这个文件夹，数据不丢。'))

        layout.addStretch(1)
        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)
