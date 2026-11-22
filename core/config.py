import os
import json
import sys
import threading
import time

DEFAULT_DATA_ROOT = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), '.mclauncherpy')

SETTINGS_FILE = 'launcher-config.json'
SUBDIRS = ['versions', 'libraries', 'assets', 'instances', 'accounts', 'mods_cache']

# 数据目录“记忆文件”：独立于数据目录本身存放，用于记住用户上一次选择的
# 数据存放位置。即使数据目录被删除/拔出（如 U 盘），也能据此重新弹窗让用户再选。
DATA_DIR_MARKER = 'mclauncher_data_dir.txt'


def _marker_path():
    """记忆文件存放位置：exe 同目录优先（便携），若不可写则放 APPDATA。"""
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if os.access(exe_dir, os.W_OK):
        return os.path.join(exe_dir, DATA_DIR_MARKER)
    app_dir = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                           '.mclauncherpy_loc')
    try:
        os.makedirs(app_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(app_dir, DATA_DIR_MARKER)


def _decode_text(raw):
    """按多种编码尝试解码文本内容。

    数据目录记忆文件可能由不同来源写入：启动器自己写的是 utf-8，
    而安装器（NSIS）写的是系统 ANSI 代码页（中文系统为 GBK），
    也可能是 UTF-16。这里依次尝试，保证都能读出来。
    """
    if not raw:
        return ''
    for enc in ('utf-8-sig', 'utf-8', 'gbk', 'mbcs', 'utf-16'):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    try:
        return raw.decode('utf-8', errors='replace')
    except Exception:
        return ''


def _read_text_file(path):
    """读取文本文件并解码，失败返回空串。"""
    try:
        with open(path, 'rb') as f:
            raw = f.read()
    except Exception:
        return ''
    return _decode_text(raw).strip()


def read_saved_data_dir():
    """读取上次用户选择的数据目录；未设置或读取失败返回 None。"""
    p = _read_text_file(_marker_path())
    return p or None


def write_saved_data_dir(path):
    """把用户选择的数据目录写入记忆文件。"""
    ok = False
    try:
        with open(_marker_path(), 'w', encoding='utf-8') as f:
            f.write(path or '')
        ok = True
    except Exception:
        pass
    # 同时登记到全局清单：换版本、换 exe 位置后仍能找回这份数据
    register_known_data_dir(path)
    return ok


def resolve_data_dir():
    """返回可用的数据目录：若记忆的路径仍存在则返回它；否则返回 None（需向导）。"""
    p = read_saved_data_dir()
    if p and os.path.isdir(p):
        return p
    return None


# ---------------------------------------------------------------------------
# 全局“已知数据目录”清单
#
# 记忆文件默认放在 exe 同目录（便携优先），一旦换了 exe 位置或换了启动器版本
# 就找不到了。这里额外在 APPDATA 下维护一份清单，把用过的数据目录记下来，
# 新版本首次启动时可以据此自动沿用旧数据，不必重新配置。
# ---------------------------------------------------------------------------
GLOBAL_LOC_DIR = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')), '.mclauncherpy_loc')
KNOWN_DIRS_FILE = 'known_data_dirs.txt'
MAX_KNOWN_DIRS = 20


def _global_dir():
    d = GLOBAL_LOC_DIR
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _global_known_path():
    return os.path.join(_global_dir(), KNOWN_DIRS_FILE)


def read_known_data_dirs():
    """读全局已知数据目录清单（最近的在前）。"""
    out = []
    try:
        raw = open(_global_known_path(), 'rb').read()
    except Exception:
        return out
    for line in _decode_text(raw).splitlines():
        p = line.strip()
        if p and p not in out:
            out.append(p)
    return out


def register_known_data_dir(path):
    """把数据目录登记进全局清单（去重、最新的在前）。"""
    if not path:
        return False
    p = os.path.abspath(path)
    dirs = [d for d in read_known_data_dirs()
            if os.path.normcase(d) != os.path.normcase(p)]
    dirs.insert(0, p)
    dirs = dirs[:MAX_KNOWN_DIRS]
    try:
        with open(_global_known_path(), 'w', encoding='utf-8') as f:
            f.write('\n'.join(dirs))
        return True
    except Exception:
        return False


def _safe_listdir(d):
    try:
        return os.listdir(d)
    except Exception:
        return []


def inspect_data_dir(path):
    """检查目录里是否已有「启动器可用文件」。

    可用文件 = 已安装的游戏版本、依赖库、资源、账号、实例、启动器配置。
    官方启动器的 .minecraft 与本启动器的数据目录结构一致（versions /
    libraries / assets），因此同样能被识别与沿用。
    返回信息字典；目录不存在时返回 None。

    kind 字段区分来源：
      'own'     —— 本启动器自己的数据目录（有 launcher-config.json 或
                   instances/*/instance.json），可以放心自动沿用
      'other'   —— 别的启动器（官方 / PCL / HMCL 等）的目录，结构兼容但
                   账号格式不同，只能作为「可选目标」提示，绝不自动沿用
    """
    if not path or not os.path.isdir(path):
        return None
    info = {'path': os.path.abspath(path), 'accounts': 0, 'versions': 0,
            'instances': 0, 'libraries': False, 'assets': False,
            'config': False, 'usable': False, 'score': 0, 'kind': 'other'}
    if os.path.isfile(os.path.join(path, SETTINGS_FILE)):
        info['config'] = True
    acc = os.path.join(path, 'accounts')
    if os.path.isdir(acc):
        info['accounts'] = sum(1 for f in _safe_listdir(acc) if f.endswith('.json'))
    vd = os.path.join(path, 'versions')
    if os.path.isdir(vd):
        info['versions'] = sum(1 for d in _safe_listdir(vd)
                                if os.path.isdir(os.path.join(vd, d)))
    idir = os.path.join(path, 'instances')
    if os.path.isdir(idir):
        info['instances'] = sum(1 for d in _safe_listdir(idir)
                                if os.path.isdir(os.path.join(idir, d)))
    info['libraries'] = bool(_safe_listdir(os.path.join(path, 'libraries')))
    info['assets'] = bool(_safe_listdir(os.path.join(path, 'assets')))
    info['usable'] = bool(info['config'] or info['accounts'] or info['versions']
                          or info['instances'] or info['libraries'] or info['assets'])
    # 判定是不是「本启动器自己的」目录：
    #   有 launcher-config.json → 一定是本启动器写的
    #   instances/<名>/instance.json → 本启动器独有的实例格式
    own = info['config']
    if not own:
        for name in _safe_listdir(idir):
            if os.path.isfile(os.path.join(idir, name, 'instance.json')):
                own = True
                break
    info['own'] = own
    info['kind'] = 'own' if own else 'other'
    info['score'] = (info['config'] * 40 + info['accounts'] * 20
                     + info['versions'] * 8 + info['instances'] * 5
                     + (8 if info['libraries'] else 0)
                     + (8 if info['assets'] else 0))
    if own:
        # 本启动器的目录永远排在其它启动器目录前面
        info['score'] += 1000
    return info


def _scan_roots():
    """可能存放启动器数据的根目录（只往下扫一层，够用且不慢）。"""
    if SCAN_ROOTS_OVERRIDE is not None:
        return list(SCAN_ROOTS_OVERRIDE)
    roots = []
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    home = os.path.expanduser('~')
    if exe_dir:
        roots.append(exe_dir)
        roots.append(os.path.dirname(exe_dir))
    for p in (os.environ.get('APPDATA', ''),
              os.environ.get('LOCALAPPDATA', ''),
              os.path.join(home, 'Desktop'),
              os.path.join(home, 'Documents'),
              os.path.join(home, 'Downloads')):
        if p:
            roots.append(p)
    # 各盘根目录：数据目录常被放在 D:\MC、D:\我的世界 之类的地方
    for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
        drv = letter + ':\\'
        if os.path.isdir(drv):
            roots.append(drv)
    out, seen = [], set()
    for r in roots:
        try:
            r = os.path.abspath(r)
        except Exception:
            continue
        k = os.path.normcase(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


_SCAN_MAX_CHILDREN = 400
_SCAN_BUDGET = 4.0        # 扫描总时间上限（秒），超时就用已有结果
# 目录里出现这些名字之一，才值得进一步检查
_QUICK_MARKERS = (SETTINGS_FILE, 'versions', 'libraries', 'assets', 'accounts',
                  'instances', DATA_DIR_MARKER)

# 测试用：限定扫描根目录（None = 用默认根目录）
SCAN_ROOTS_OVERRIDE = None


def _looks_candidate(path):
    """快速预筛：目录里有没有可能是启动器数据的标志物。"""
    try:
        for name in _QUICK_MARKERS:
            if os.path.exists(os.path.join(path, name)):
                return True
    except Exception:
        pass
    return False


def _read_marker_in(folder):
    """读某个目录下的数据目录记忆文件（其他版本启动器留下的线索）。"""
    try:
        p = os.path.join(folder, DATA_DIR_MARKER)
        if os.path.isfile(p):
            v = _read_text_file(p)
            return v or None
    except Exception:
        pass
    return None


def find_existing_data_dirs(include=None, budget=_SCAN_BUDGET):
    """扫描本机，找出所有「已有启动器可用文件」的目录，按可信度从高到低。

    include：额外要检查的路径（例如当前正在使用的数据目录）。
    budget：扫描时间预算（秒），避免在磁盘很大的机器上长时间卡住。
    """
    cands, seen = [], set()
    deadline = time.time() + max(0.5, budget)

    def add(p):
        if not p:
            return
        try:
            p = os.path.abspath(p)
        except Exception:
            return
        k = os.path.normcase(p)
        if k in seen:
            return
        seen.add(k)
        info = inspect_data_dir(p)
        if info and info.get('usable'):
            cands.append(info)

    for p in read_known_data_dirs():
        add(p)
    add(include)
    for root in _scan_roots():
        if time.time() > deadline:
            break
        add(root)
        # 根目录自身可能就带着记忆文件（如 exe 所在目录）
        m = _read_marker_in(root)
        if m:
            add(m)
        try:
            entries = os.listdir(root)
        except Exception:
            continue
        for name in entries[:_SCAN_MAX_CHILDREN]:
            if time.time() > deadline:
                break
            sub = os.path.join(root, name)
            try:
                if not os.path.isdir(sub):
                    continue
            except Exception:
                continue
            if not _looks_candidate(sub):
                continue
            add(sub)
            # 其它版本启动器的 exe 目录里通常留着数据目录记忆文件
            m = _read_marker_in(sub)
            if m:
                add(m)

    def mtime(i):
        try:
            return os.path.getmtime(i['path'])
        except Exception:
            return 0

    cands.sort(key=lambda i: (-i['score'], -mtime(i)))
    return cands


def pick_best_data_dir(exclude=None, own_only=False):
    """挑一个最可信的「已有启动器可用文件」的目录；没有则返回 None。

    own_only=True 时只考虑本启动器自己的数据目录（其它启动器的目录
    账号格式不同，混用会出乱子，只能当可选目标让用户手动挑）。
    """
    ex = os.path.normcase(os.path.abspath(exclude)) if exclude else None
    for info in find_existing_data_dirs():
        if ex and os.path.normcase(info['path']) == ex:
            continue
        if own_only and not info.get('own'):
            continue
        return info['path']
    return None


def _quick_roots():
    """启动时快速查找用的根目录（不做全盘扫描，保证秒开）。"""
    if SCAN_ROOTS_OVERRIDE is not None:
        return list(SCAN_ROOTS_OVERRIDE)
    roots = []
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    home = os.path.expanduser('~')
    if exe_dir:
        roots.append(exe_dir)
        roots.append(os.path.dirname(exe_dir))
    appdata = os.environ.get('APPDATA', '')
    if appdata:
        roots.append(appdata)
        roots.append(os.path.join(appdata, '.mclauncherpy'))
        roots.append(os.path.join(appdata, '.minecraft'))
    roots.append(os.path.join(home, 'Desktop'))
    roots.append(os.path.join(home, 'Documents'))
    roots.append(os.path.join(home, 'Downloads'))
    out, seen = [], set()
    for r in roots:
        try:
            r = os.path.abspath(r)
        except Exception:
            continue
        k = os.path.normcase(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def quick_find_data_dirs(include=None):
    """启动时的快速查找：只查常见位置，毫秒级返回。

    命中的判据与 find_existing_data_dirs 一致（目录里确有启动器可用文件）。
    """
    cands, seen = [], set()

    def add(p):
        if not p:
            return
        try:
            p = os.path.abspath(p)
        except Exception:
            return
        k = os.path.normcase(p)
        if k in seen:
            return
        seen.add(k)
        info = inspect_data_dir(p)
        if info and info.get('usable'):
            cands.append(info)

    # 1) 全局登记表：跨版本、跨 exe 位置都能找回用过的目录
    for p in read_known_data_dirs():
        add(p)
    # 2) 当前正在用的
    add(include)
    # 3) 常见位置 + 它们的下一层
    for root in _quick_roots():
        add(root)
        m = _read_marker_in(root)
        if m:
            add(m)
        try:
            entries = os.listdir(root)
        except Exception:
            continue
        for name in entries[:_SCAN_MAX_CHILDREN]:
            sub = os.path.join(root, name)
            try:
                if not os.path.isdir(sub):
                    continue
            except Exception:
                continue
            if not _looks_candidate(sub):
                continue
            add(sub)
            # 其它版本启动器的 exe 目录里通常留着数据目录记忆文件
            m = _read_marker_in(sub)
            if m:
                add(m)

    def mtime(i):
        try:
            return os.path.getmtime(i['path'])
        except Exception:
            return 0

    cands.sort(key=lambda i: (-i['score'], -mtime(i)))
    return cands

_BMCLAPI_BASE = 'https://bmclapi2.bangbang93.com'
_MCBBS_BASE = 'https://download.mcbbs.net'


def _build_rewrite(base):
    """根据镜像根地址生成「官方 URL → 镜像 URL」的改写规则。

    绝大多数 BMCLAPI 兼容镜像都遵循同一套路径结构（根地址后接 /libraries、
    /assets、/maven 等），所以只要用户提供根地址即可复用这套规则，
    无需逐条手动配置。
    """
    base = (base or '').rstrip('/')
    return [
        ('https://launcher.mojang.com/', base + '/'),
        ('https://piston-meta.mojang.com/', base + '/'),
        ('https://piston-data.mojang.com/', base + '/'),
        ('https://libraries.minecraft.net/', base + '/libraries/'),
        ('https://resources.download.minecraft.net/', base + '/assets/'),
        ('https://maven.minecraftforge.net/', base + '/maven/'),
        ('https://files.minecraftforge.net/maven/', base + '/maven/'),
    ]


# 自定义镜像根地址：运行时由设置注入；为空时「自定义」源退化为官方源
CUSTOM_BASE = ''
_CUSTOM_LOCK = threading.Lock()


def set_custom_base(url):
    """设置自定义镜像根地址（ui/settings 在加载与保存时调用）。"""
    global CUSTOM_BASE
    with _CUSTOM_LOCK:
        CUSTOM_BASE = (url or '').strip().rstrip('/')


def _custom_rewrite():
    if not CUSTOM_BASE:
        return None
    return _build_rewrite(CUSTOM_BASE)


DOWNLOAD_SOURCES = {
    'official': {
        'name': '官方',
        'rewrite': None,
    },
    'bmclapi': {
        'name': 'BMCLAPI',
        'rewrite': _build_rewrite(_BMCLAPI_BASE),
    },
    'mcbbs': {
        'name': 'MCBBS',
        'rewrite': _build_rewrite(_MCBBS_BASE),
    },
    'custom': {
        'name': '自定义',
        'rewrite': None,
    },
}

DEFAULT_SETTINGS = {
    'dataRoot': DEFAULT_DATA_ROOT,
    'downloadSource': 'bmclapi',
    'customSourceUrl': '',
    'javaPath': 'java',
    'maxMemory': 2048,
    'minMemory': 512,
    'javaArgs': '',
    'gameArgs': '',
    'concurrency': 16,
    'segmented': True,
    'proxy': '',
    'theme': 'light',
    'msaClientId': '',
    'lastAccount': None,
    'lastInstance': None,
    'showStagePanel': True,
    'skipOnboarding': True,
    'gameLang': 'zh_cn',
    'notifySound': True,
    'notifyToast': True,
    'elastic': True,
}


def rewrite_url(url, source='bmclapi'):
    if source == 'custom':
        rules = _custom_rewrite()
        if not rules:
            return url
        for a, b in rules:
            if url.startswith(a):
                return b + url[len(a):]
        return url
    src = DOWNLOAD_SOURCES.get(source)
    if not src or not src.get('rewrite'):
        return url
    for a, b in src['rewrite']:
        if url.startswith(a):
            return b + url[len(a):]
    return url


def ensure_data_root(data_root):
    os.makedirs(data_root, exist_ok=True)
    for s in SUBDIRS:
        os.makedirs(os.path.join(data_root, s), exist_ok=True)


def load_settings(data_root=None):
    data_root = data_root or DEFAULT_DATA_ROOT
    path = os.path.join(data_root, SETTINGS_FILE)
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            settings.update(data)
        except Exception:
            pass
    set_custom_base(settings.get('customSourceUrl', ''))
    settings['dataRoot'] = data_root
    ensure_data_root(data_root)
    return settings


def save_settings(settings):
    set_custom_base(settings.get('customSourceUrl', ''))
    ensure_data_root(settings['dataRoot'])
    path = os.path.join(settings['dataRoot'], SETTINGS_FILE)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
