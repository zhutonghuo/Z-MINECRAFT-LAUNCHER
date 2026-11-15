import os
import re
import shutil
import subprocess

SCAN_ROOTS = [
    r'C:\Program Files\Java',
    r'C:\Program Files (x86)\Java',
    r'D:\MSL\Java',
    r'C:\Program Files\Eclipse Adoptium',
    r'C:\Program Files\BellSoft',
    r'C:\Program Files\Amazon Corretto',
    r'C:\Program Files\Microsoft',
    r'C:\Program Files\Zulu',
    r'C:\Java',
    r'D:\Java',
]


def parse_java_version(text):
    m = re.search(r'version "([^"]+)"', text) or re.search(r'version ([^\s]+)', text)
    if not m:
        return None
    ver = m.group(1)
    parts = ver.split('.')
    if parts[0] == '1' and len(parts) > 1:
        try:
            major = int(parts[1])
        except ValueError:
            major = 0
    else:
        try:
            major = int(parts[0].split('+')[0])
        except ValueError:
            major = 0
    return {'raw': ver, 'major': major}


def _probe(java_bin):
    try:
        out = subprocess.run([java_bin, '-version'], capture_output=True, text=True, timeout=10)
        info = parse_java_version(out.stdout + out.stderr)
        if not info:
            return None
        return {'path': java_bin, 'major': info['major'], 'raw': info['raw']}
    except Exception:
        return None


def detect_java_runtimes():
    found = []
    seen = set()

    def add(java_bin):
        if not java_bin or not os.path.isfile(java_bin):
            return
        real = os.path.realpath(java_bin)
        if real in seen:
            return
        info = _probe(real)
        if not info:
            return
        seen.add(real)
        found.append(info)

    p = shutil.which('java')
    if p:
        add(p)
    jh = os.environ.get('JAVA_HOME')
    if jh:
        add(os.path.join(jh, 'bin', 'java.exe'))
        add(os.path.join(jh, 'bin', 'java'))
    for root in SCAN_ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            if dirpath[len(root):].count(os.sep) > 4:
                dirs[:] = []
                continue
            if 'java.exe' in files:
                add(os.path.join(dirpath, 'java.exe'))
            elif 'java' in files:
                add(os.path.join(dirpath, 'java'))
    found.sort(key=lambda x: -x['major'])
    return found


def pick_java(runtimes, want_major=None):
    """挑选一个 Java。

    want_major 来自版本 json 的 javaVersion.majorVersion（如 26.x 需要 25），
    优先精确匹配，其次选不低于要求的版本，最后才退回最高版本。
    """
    if not runtimes:
        return None
    if want_major:
        for r in runtimes:
            if r['major'] == want_major:
                return r['path']
        for r in runtimes:
            if r['major'] >= want_major:
                return r['path']
    return runtimes[0]['path']


def _parse_mc(v):
    m = re.match(r'^(\d+)\.(\d+)(?:\.(\d+))?', v or '')
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def required_java_major(mc_version):
    """根据 Minecraft 版本返回需要的 Java 大版本。

    ≤1.16.5 → 8；1.17–1.20.4 → 17；≥1.20.5 → 21。
    无法解析的版本（多为新快照）默认 21，符合新版 MC 趋势。
    """
    p = _parse_mc(mc_version)
    if not p:
        return 21
    maj, mino, pat = p
    if maj != 1:
        return 21
    if mino <= 16:
        return 8
    if (mino, pat) < (20, 5):
        return 17
    return 21


ADOPTIUM_INFO = 'https://api.adoptium.net/v3/assets/feature_releases/{major}/ga'
ADOPTIUM_LATEST = ('https://api.adoptium.net/v3/binary/latest/{major}/ga/'
                   'windows/x64/jdk/hotspot/normal/eclipse?archive_type=zip')


def _java_download_url(major):
    """返回 (url, size)。优先拿带 size 的精确包链接，失败退回 latest。"""
    try:
        from core.http import get_json
        params = {'image_type': 'jdk', 'architecture': 'x64',
                  'operating_system': 'windows', 'vendor': 'eclipse',
                  'page_size': '1', 'project': 'jdk'}
        data = get_json(ADOPTIUM_INFO.format(major=major), timeout=25, params=params)
        if isinstance(data, list) and data and data[0].get('binaries'):
            pkg = data[0]['binaries'][0].get('package', {})
            link = pkg.get('link')
            if link:
                return link, pkg.get('size')
    except Exception:
        pass
    return ADOPTIUM_LATEST.format(major=major), None


def _find_java_exe(root):
    for dp, _dirs, files in os.walk(root):
        for f in files:
            if f.lower() == 'java.exe':
                return os.path.join(dp, f)
    return None


def ensure_java_for_version(mc_version, data_root, source='bmclapi',
                            on_progress=None, log=None):
    """确保安装该 MC 版本时存在合适的 Java。

    返回 (java_path, downloaded)。
    - 系统已装有合适版本：直接返回系统路径，downloaded=False。
    - 系统没有：自动下载 JDK 到 data_root/runtimes/jre-{major}/ 并解压，
      downloaded=True。已存在则复用，不重复下载。
    """
    import zipfile

    from core.download import download_file

    major = required_java_major(mc_version)
    runtimes = detect_java_runtimes()
    system_path = pick_java(runtimes, major)
    if system_path:
        return system_path, False

    target = os.path.join(data_root, 'runtimes', 'jre-%d' % major)
    os.makedirs(target, exist_ok=True)
    java_bin = os.path.join(target, 'bin', 'java.exe')
    if os.path.isfile(java_bin):
        return java_bin, False

    if log:
        log('未检测到 Java %d，正在自动下载并安装...' % major)
    url, size = _java_download_url(major)
    zip_path = os.path.join(target, 'download.zip')
    prog = {'stage': '下载 Java %d（自动）' % major, 'done': 0,
            'total': size or 0, 'speed': 0, 'name': 'jdk-%d.zip' % major}

    def on_delta(n):
        if on_progress and size:
            prog['done'] = min(size, prog['done'] + n)
            on_progress(dict(prog))

    ok = download_file(url, zip_path, size=size, on_delta=on_delta,
                       name='jdk-%d.zip' % major)
    if not ok and size:
        ok = download_file(ADOPTIUM_LATEST.format(major=major), zip_path,
                           on_delta=on_delta, name='jdk-%d.zip' % major)
    if not ok or not os.path.isfile(zip_path):
        raise Exception('Java %d 自动下载失败（官方源暂不可达）。请手动安装 '
                        'Java %d 后重试，或在「设置」里指定 Java 路径。'
                        % (major, major))

    if log:
        log('正在解压 Java %d...' % major)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(target)
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass
    found = _find_java_exe(target)
    if not found:
        raise Exception('Java %d 解压后未找到 java.exe，安装中断。' % major)
    return found, True
