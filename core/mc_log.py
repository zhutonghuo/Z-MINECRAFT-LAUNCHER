# -*- coding: utf-8 -*-
"""把 Minecraft 启动器/游戏的控制台输出翻译成中文“人话”，方便普通玩家看懂。

设计原则：
  - stage(msg)         ：输出一行的“阶段提示”（带【】前缀），用于我们自己的流程说明。
  - humanize(raw_line) ：把一条原始 MC 日志（多为英文）翻译成一句中文说明；
                         若无法识别则返回 None，调用方仍会原样显示原文。
  - 控制台里「原文」与「中文说明」都保留，既可读又可排错。
"""
import re

# 常见英文日志片段 -> 中文说明（按顺序匹配，命中即返回）
PATTERNS = [
    (re.compile(r'Loading (minecraft|Minecraft).*?(\d+\.\d+)', re.I),
     lambda m: '正在加载 Minecraft 客户端（版本 %s）' % m.group(2)),
    (re.compile(r'Setting user:\s*([^\s]+)', re.I),
     lambda m: '已设置玩家角色：%s' % m.group(1)),
    (re.compile(r'authlib[-_]injector', re.I),
     lambda m: '第三方登录（authlib-injector）已注入，将以自定义账号服务器验证'),
    (re.compile(r'LWJGL Version:\s*([\d.]+)', re.I),
     lambda m: '图形库 LWJGL 版本：%s' % m.group(1)),
    (re.compile(r'(openGL|GL) version', re.I),
     lambda m: '检测到 OpenGL 版本信息（显卡/驱动相关）'),
    (re.compile(r'(?i)Could not create.*(pixel format|context|opengl)', re.I),
     lambda m: '❌ 无法创建 OpenGL 画面：通常是显卡驱动过旧或不支持，请更新显卡驱动'),
    (re.compile(r'(?i)Pixel format not accelerated', re.I),
     lambda m: '❌ 显卡像素格式不被加速：请更新显卡驱动，或在设置里降低显卡选项'),
    (re.compile(r'(?i)NoClassDefFoundError|Could not find or load main class', re.I),
     lambda m: '❌ 找不到主类：Java 路径或版本不对，请在“设置”里换一个 Java（建议用游戏自带/匹配版本）'),
    (re.compile(r'(?i)UnsupportedClassVersionError', re.I),
     lambda m: '❌ Java 版本过低：当前 Java 太旧，无法运行该版本，请升级 Java'),
    (re.compile(r'(?i)OutOfMemoryError|GC overhead limit', re.I),
     lambda m: '❌ 内存不足（Java 堆溢出）：请在“设置”里调大“最大内存”，并关闭其他占用内存的程序'),
    (re.compile(r'Welcome to Minecraft', re.I),
     lambda m: '这是官方首次启动引导页（选语言/无障碍），不是试玩版；点 Continue 即进主菜单'),
    (re.compile(r'Failed to fetch user properties', re.I),
     lambda m: '离线账号无法拉取皮肤属性（属正常现象，不影响游戏）'),
    (re.compile(r'(?i)Could not authorize you against Realms|Failed to fetch Realms feature flags', re.I),
     lambda m: '离线账号无法访问 Realms（属正常现象，不影响游戏）'),
    (re.compile(r'(?i)RealmsServiceException', re.I),
     lambda m: 'Realms 服务不可用（离线账号属正常现象，不影响游戏）'),
    (re.compile(r'(?i)InvalidCredentialsException|MinecraftClientHttpException', re.I),
     lambda m: '账号令牌未通过官方校验（离线账号属正常现象，不影响进入游戏）'),
    (re.compile(r'(?i)Failed to download|无法下载|Download failed', re.I),
     lambda m: '⚠ 下载失败：可能是网络或镜像源问题，可到“设置”里切换下载源后重试'),
    (re.compile(r'(?i)java\.lang\.Exception|Exception in thread', re.I),
     lambda m: '❌ 游戏抛出异常（见上方堆栈）'),
    (re.compile(r'(?i)\b(FATAL|ERROR)\b', re.I),
     lambda m: '❌ 出现错误（见上方日志）'),
    (re.compile(r'(?i)\bwarn(ing)?\b', re.I),
     lambda m: '⚠ 警告（一般不影响启动，但可留意）'),
    (re.compile(r'(?i)Reloading ResourceManager|Reloading', re.I),
     lambda m: '正在重新加载资源（资源包/语言等）'),
    (re.compile(r'(?i)Synthesizing (audio|sound)', re.I),
     lambda m: '正在初始化音频'),
    (re.compile(r'(?i)OpenAL', re.I),
     lambda m: '音频系统 OpenAL 初始化中'),
    (re.compile(r'(?i)Initializing (game|mixer|blocks|items)', re.I),
     lambda m: '正在初始化游戏内容（方块/物品等）'),
    (re.compile(r'(?i)Starting (minecraft|integrated|server)', re.I),
     lambda m: '游戏世界/服务端启动中'),
    (re.compile(r'(?i)Stopping|Shutting down', re.I),
     lambda m: '正在关闭游戏/释放资源'),
]


def stage(msg):
    """格式化一条阶段提示（我们自己的中文流程说明）。"""
    return '◆ ' + msg


def humanize(raw):
    """把一条原始日志翻译成中文说明；识别不了返回 None。"""
    if not raw:
        return None
    line = raw.strip()
    low = line.lower()
    # 跳过纯进度条/空白行
    if not line or line in ('>',):
        return None
    # 堆栈帧行不再重复解释（真正的错误行已给过说明）
    if line.startswith('at ') or line.startswith('... '):
        return None
    for rx, fn in PATTERNS:
        m = rx.search(line)
        if m:
            try:
                return fn(m)
            except Exception:
                return None
    return None


# 启动进度台：把游戏日志映射到「步骤文字 + 进度百分比」（pct 越大越接近进游戏）
# 每个条目：(正则, 文字或函数, 百分比)
STAGE_PATTERNS = [
    (re.compile(r'Loading (minecraft|Minecraft).*?(\d+\.\d+)', re.I),
     (lambda m: '正在加载 Minecraft 客户端（版本 %s）' % m.group(2)), 25),
    (re.compile(r'Setting user:\s*([^\s]+)', re.I),
     (lambda m: '已设置玩家角色：%s' % m.group(1)), 30),
    (re.compile(r'authlib[-_]injector', re.I),
     '第三方登录（authlib-injector）已注入，正在连接自定义账号服务器', 32),
    (re.compile(r'LWJGL Version:\s*([\d.]+)', re.I),
     (lambda m: '初始化图形库 LWJGL（版本 %s）' % m.group(1)), 45),
    (re.compile(r'(?i)OpenAL', re.I),
     '正在初始化音频系统（OpenAL）', 60),
    (re.compile(r'(?i)Synthesizing (audio|sound)', re.I),
     '正在初始化音频', 60),
    (re.compile(r'(?i)Reloading ResourceManager|Reloading', re.I),
     '正在加载资源（资源包 / 语言）', 75),
    (re.compile(r'(?i)Initializing (game|mixer|blocks|items)', re.I),
     '正在初始化游戏内容（方块 / 物品）', 78),
    (re.compile(r'(?i)Starting (minecraft|integrated|server)', re.I),
     '游戏世界启动中', 90),
]


def log_stage(raw):
    """把一条原始日志识别为启动阶段（文字, 百分比）；识别不了返回 None。"""
    if not raw:
        return None
    line = raw.strip()
    if not line:
        return None
    for rx, txt, pct in STAGE_PATTERNS:
        m = rx.search(line)
        if m:
            try:
                if callable(txt):
                    return (txt(m), pct)
                return (txt, pct)
            except Exception:
                return None
    return None


def account_desc(acc):
    """账号中文描述"""
    if not acc:
        return '未登录（请先在左侧登录账号）'
    name = acc.get('name') or '未知'
    t = acc.get('type')
    if t == 'microsoft':
        return '%s（正版微软账号）' % name
    if t == 'yggdrasil':
        srv = acc.get('server') or ''
        host = srv.split('//')[-1].split('/')[0] or '自定义服务器'
        return '%s（第三方账号 · %s）' % (name, host)
    return '%s（离线账号）' % name


def auth_hint(acc):
    """账号授权方式说明：告诉用户进游戏后会是哪种体验，避免误判成“试玩版”"""
    if not acc:
        return ''
    t = acc.get('type')
    if t == 'offline':
        return ('离线账号：以离线身份进入游戏，可正常单人游玩；'
                '无法访问正版验证的服务器与 Realms（这是正常现象，不是试玩版）')
    if t == 'yggdrasil':
        return '第三方账号：通过 authlib-injector 由自定义服务器验证，进入后为正常游玩界面'
    return '正版微软账号：令牌已通过官方校验，进入后为正常游玩界面'
