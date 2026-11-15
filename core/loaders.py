# -*- coding: utf-8 -*-
"""加载器（Fabric / Quilt / Forge / NeoForge / OptiFine）下载与安装。

设计：
- Fabric / Quilt：从各自的官方 Meta 拉取「合并后的版本 JSON（profile）」，
  把它当作一个普通的版本（inheritsFrom 原版）写入 versions/<id>/<id>.json，
  然后复用 install_vanilla 的下载管线（它会顺着 inheritsFrom 把原版客户端、
  库、资源一并下载）。这是最干净的方案，不需要跑任何 GUI 安装器。
- Forge / NeoForge / OptiFine：下载官方 installer.jar，用 java 以 headless 方式
  执行 `--installClient <数据根目录>`，由安装器生成版本 profile 与必要的库。
  这部分依赖安装器能 headless 运行，若失败会给出明确中文提示。

所有函数都尽量在出错时抛出带「人话」的异常，方便 UI 直接展示。
"""
import os
import json
import shutil
import subprocess
import tempfile

from core.config import rewrite_url
from core.http import get_json, get_bytes, friendly_error
from core.manifest import get_manifest, MANIFEST_URL
from core.installer import install_vanilla, is_installed

FABRIC_META = 'https://meta.fabricmc.net/v2'
QUILT_META = 'https://meta.quiltmc.org/v3'

# 国内镜像基址（BMCLAPI）。实测这些路径返回内容与官方完全一致，
# 但在国内速度快 3 倍以上，用于「查询加载器列表」这种纯元数据请求。
_BMCLAPI = 'https://bmclapi2.bangbang93.com'

# 中科大镜像：只同步 BMCLAPI 的 /maven/ 部分（Forge / NeoForge 元数据）。
# 实测直接命中不重定向、0.35s；走 bmclapi2 会被 302 到 mirrors.cernet.edu.cn
# 或 sakura 节点，那几个节点很慢（实测单次 7s+）。
_USTC = 'https://mirrors.ustc.edu.cn/bmclapi'

# Maven 元数据的进程内缓存（Forge 的元数据很大，避免重复下载）
_MAVEN_CACHE = {}

# 各加载器元数据的候选源，按「国内优先 → 官方兜底」排列。
# 弹窗要同时查 5 个加载器，全部走海外源会很慢，因此优先用国内镜像。
META_SOURCES = {
    'fabric': [
        _BMCLAPI + '/fabric-meta/v2',      # 国内，实测 0.5s
        FABRIC_META,                        # 官方兜底
    ],
    'quilt': [
        _BMCLAPI + '/quilt-meta/v3',       # 国内
        QUILT_META,                         # 官方兜底
    ],
}

# 加载器类型（顺序即 UI 下拉顺序）
LOADER_TYPES = [
    ('vanilla', '原版（Vanilla）'),
    ('fabric', 'Fabric'),
    ('quilt', 'Quilt'),
    ('forge', 'Forge'),
    ('neoforge', 'NeoForge'),
    ('optifine', 'OptiFine（光影加载器）'),
]


def _meta_urls(loader_type, path, source='bmclapi'):
    """列出某加载器元数据接口的候选 URL（国内镜像优先，官方兜底）。"""
    bases = META_SOURCES.get(loader_type)
    if not bases:
        return []
    urls = []
    for b in bases:
        urls.append(b + path)
    # 自定义镜像源：把用户填的根地址也当作候选（若其结构兼容 BMCLAPI）
    if source == 'custom':
        from core.config import get_custom_base
        cb = (get_custom_base() or '').rstrip('/')
        if cb:
            urls.insert(0, cb + '/fabric-meta/v2' + path
                        if loader_type == 'fabric'
                        else cb + '/quilt-meta/v3' + path)
    return urls


def _get_meta_json(loader_type, path, source='bmclapi', timeout=12):
    """按候选源列表依次尝试取 JSON，第一个成功即返回。

    超时故意设得较短（默认 12s），这样某个源卡住时不会把整个弹窗拖死，
    会自动降级到下一个源。
    """
    urls = _meta_urls(loader_type, path, source)
    if not urls:
        raise Exception('未知加载器：%s' % loader_type)
    last = None
    for u in urls:
        try:
            return get_json(u, tries=2, timeout=timeout)
        except Exception as e:
            last = e
            continue
    raise last if last else Exception('无法获取 %s 元数据' % loader_type)


def _get_json(url, source='bmclapi'):
    try:
        return get_json(rewrite_url(url, source), tries=2, timeout=25)
    except Exception:
        # 这些 Meta 服务没有被我们的镜像覆盖，直接用官方地址再试一次
        return get_json(url, tries=2, timeout=25)


def _base_version_url(version_id, source='bmclapi'):
    """从官方版本清单里查出某原版版本的 JSON 地址（用于确保原版已安装）。"""
    m = get_manifest(source)
    for v in m.get('versions', []):
        if v.get('id') == version_id:
            return rewrite_url(v['url'], source)
    raise Exception('在版本清单中找不到原版版本：%s' % version_id)


def _ensure_base(data_root, source, mc_version, log, progress_cb, item_cb, concurrency, segmented):
    """确保原版基版本已安装（客户端 jar + 库 + 资源）。Fabric/Forge 等都依赖它。"""
    if is_installed(data_root, mc_version):
        if log:
            log('原版 %s 已安装，跳过' % mc_version)
        return
    url = _base_version_url(mc_version, source)
    if log:
        log('正在安装原版基版本 %s（客户端、库与资源）...' % mc_version)
    install_vanilla(data_root, source, mc_version, url,
                    progress_cb=progress_cb, item_cb=item_cb,
                    concurrency=concurrency, segmented=segmented)


# ---------------------------------------------------------------- Fabric
def fabric_game_versions(source='bmclapi'):
    data = _get_meta_json('fabric', '/versions/game', source)
    out = []
    for e in data:
        out.append(e['version'])
    # 稳定的排前面
    out.sort(key=lambda v: (0 if any(v == s.get('version') and s.get('stable')
                                     for s in data) else 1, v))
    return out


def fabric_loader_versions(mc_version=None, source='bmclapi'):
    """取 Fabric 加载器版本。

    指定 mc_version 时用 /versions/loader/{mc} 精确返回该版本兼容的 loader
    （下拉框里只显示真正能用的）；不指定则返回全部 loader 版本。
    """
    if mc_version:
        try:
            data = _get_meta_json('fabric', '/versions/loader/%s' % mc_version, source)
            out = []
            for e in data if isinstance(data, list) else []:
                v = (e.get('loader') or {}).get('version')
                if v:
                    out.append(v)
            if out:
                return out
        except Exception:
            pass
    data = _get_meta_json('fabric', '/versions/loader', source)
    stable = [e['version'] for e in data if e.get('stable')]
    others = [e['version'] for e in data if not e.get('stable')]
    return stable + others


def _install_fabric(data_root, source, mc_version, loader_version, log, progress_cb,
                    item_cb, concurrency, segmented):
    if log:
        log('获取 Fabric 版本 JSON（%s / loader %s）...' % (mc_version, loader_version))
    prof = _get_meta_json('fabric', '/versions/loader/%s/%s/profile/json'
                           % (mc_version, loader_version), source)
    version_id = prof.get('id')
    if not version_id:
        raise Exception('Fabric 返回的版本 JSON 缺少 id 字段')
    _ensure_base(data_root, source, mc_version, log, progress_cb, item_cb,
                 concurrency, segmented)
    vdir = os.path.join(data_root, 'versions', version_id)
    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, version_id + '.json'), 'w', encoding='utf-8') as f:
        json.dump(prof, f, ensure_ascii=False)
    if log:
        log('已写入版本 JSON，开始下载 Fabric 相关库与资源...')
    install_vanilla(data_root, source, version_id, '',
                    progress_cb=progress_cb, item_cb=item_cb,
                    concurrency=concurrency, segmented=segmented)
    return version_id


# ---------------------------------------------------------------- Quilt
def quilt_game_versions(source='bmclapi'):
    try:
        data = _get_meta_json('quilt', '/versions/game', source)
        out = [e['version'] for e in data]
        out.sort(key=lambda v: (0 if e.get('stable') else 1, v))
        return out
    except Exception:
        # Quilt 支持的 MC 版本与 Fabric 基本一致，退回到 Fabric 列表
        return fabric_game_versions(source)


def quilt_loader_versions(mc_version=None, source='bmclapi'):
    if mc_version:
        try:
            data = _get_meta_json('quilt', '/versions/loader/%s' % mc_version, source)
            out = []
            for e in data if isinstance(data, list) else []:
                v = (e.get('loader') or {}).get('version')
                if v:
                    out.append(v)
            if out:
                return out
        except Exception:
            pass
    data = _get_meta_json('quilt', '/versions/loader', source)
    stable = [e['version'] for e in data if e.get('stable')]
    others = [e['version'] for e in data if not e.get('stable')]
    return stable + others


def _install_quilt(data_root, source, mc_version, loader_version, log, progress_cb,
                   item_cb, concurrency, segmented):
    if log:
        log('获取 Quilt 版本 JSON（%s / loader %s）...' % (mc_version, loader_version))
    info = _get_meta_json('quilt', '/versions/loader/%s/%s'
                          % (mc_version, loader_version), source)
    prof = info.get('launcher_meta', {}).get('version') or info.get('profile') or info
    version_id = prof.get('id')
    if not version_id:
        raise Exception('Quilt 返回的版本 JSON 缺少 id 字段（接口可能已变动）')
    _ensure_base(data_root, source, mc_version, log, progress_cb, item_cb,
                 concurrency, segmented)
    vdir = os.path.join(data_root, 'versions', version_id)
    os.makedirs(vdir, exist_ok=True)
    with open(os.path.join(vdir, version_id + '.json'), 'w', encoding='utf-8') as f:
        json.dump(prof, f, ensure_ascii=False)
    if log:
        log('已写入版本 JSON，开始下载 Quilt 相关库与资源...')
    install_vanilla(data_root, source, version_id, '',
                    progress_cb=progress_cb, item_cb=item_cb,
                    concurrency=concurrency, segmented=segmented)
    return version_id


# ---------------------------------------------------------------- 安装器类（Forge/NeoForge/OptiFine）
def _ensure_launcher_profiles(data_root):
    """确保 data_root 下有 launcher_profiles.json。

    官方启动器会在数据目录写这个文件；自定义启动器若缺失，Forge/NeoForge/
    OptiFine 的安装器（headless --installClient 模式）会报
    "There is no minecraft launcher profile ... you need to run the launcher first!"
    并以退出码 1 失败。补一个最小合法文件即可让安装器继续。
    已存在则不动（不覆盖用户/官方启动器写的内容）。
    """
    try:
        os.makedirs(data_root, exist_ok=True)
        p = os.path.join(data_root, 'launcher_profiles.json')
        if not os.path.isfile(p):
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({'profiles': {}, 'selectedProfile': None}, f)
    except Exception:
        # 创建失败不应阻断安装主流程，最多让安装器继续报原错
        pass


def _run_installer(jar_path, data_root, java_path, log, timeout=600):
    """以 headless 方式运行 installer.jar，安装到 data_root。"""
    if not java_path or java_path in ('java', ''):
        java_path = 'java'
    # Forge/NeoForge/OptiFine 安装器在 headless 安装模式下会读取 data_root 下的
    # launcher_profiles.json；官方启动器才会生成它，自定义启动器必须自己补一个
    # 最小文件，否则安装器直接报 "There is no minecraft launcher profile" 并退出码 1。
    _ensure_launcher_profiles(data_root)
    cmd = [java_path, '-Djava.awt.headless=true', '-jar', jar_path,
           '--installClient', data_root]
    if log:
        log('运行安装器：' + ' '.join(cmd))
    # 复制一份干净的环境：彻底移除各种 JVM 工具选项注入变量。
    # 注意不能设成空串——把 JAVA_TOOL_OPTIONS 设为空字符串，JVM 仍会打印
    # "Picked up JAVA_TOOL_OPTIONS:"，某些 JDK 还会因解析空值异常退出；直接删除键才干净。
    env = dict(os.environ)
    for _k in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'):
        env.pop(_k, None)
    try:
        proc = subprocess.run(cmd, cwd=data_root, capture_output=True,
                              text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise Exception('安装器运行超时（%d 秒），可能被网络或镜像拖慢；' % timeout
                        + '可稍后重试，或手动用官方安装器安装后再由本启动器启动。')
    except FileNotFoundError:
        raise Exception('没有找到可用的 Java（%s）。请先在「设置」里配置 Java 路径。' % java_path)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or '')[-1500:]
        msg = '安装器返回错误码 %d。\n%s' % (proc.returncode, tail)
        if 'launcher profile' in tail:
            msg += ('\n\n（提示：安装器找不到 launcher_profiles.json。'
                    '启动器本应自动补建该文件；若仍出现此提示，请确认数据目录可写，'
                    '或手动在游戏数据目录下新建一个内容为 {"profiles":{}} 的 '
                    'launcher_profiles.json 后重试。）')
        raise Exception(msg)
    if log:
        log('安装器执行完成。')
    return True


def _detect_installed_version(data_root, prefix):
    """在安装器运行后，从 versions/ 里找出以 prefix 开头、且包含 .json 的版本。"""
    vdir = os.path.join(data_root, 'versions')
    if not os.path.isdir(vdir):
        return None
    best = None
    for d in sorted(os.listdir(vdir), reverse=True):
        if d.startswith(prefix) and os.path.isfile(os.path.join(vdir, d, d + '.json')):
            best = d
            break
    return best


def _maven_versions(artifact_path, source='bmclapi', data_root=None):
    """取 Maven 仓库的版本列表。

    源的选择经过实测（国内网络环境）：
    - Forge：BMCLAPI 提供 maven-metadata.json（81KB / 0.6s），
      比 .xml（213KB / 3.5s）又快又小 —— 优先 JSON。
    - NeoForge：BMCLAPI 只有 .xml（69KB / 0.7s）可取；
      官方 maven.neoforged.net 在国内基本超时，只作兜底。

    两级缓存：
    1. 进程内缓存（_MAVEN_CACHE）——同一次弹窗查询里 Forge 与 NeoForge
       都要用，重复下载会白白多花几十秒；
    2. 落盘缓存（meta_cache）——Forge 元数据很大，跨会话复用，
       第二次打开弹窗几乎零等待。
    """
    if artifact_path in _MAVEN_CACHE:
        return _MAVEN_CACHE[artifact_path]

    from core import meta_cache
    cache_key = 'maven|' + artifact_path
    if data_root:
        raw = meta_cache.get_str(data_root, cache_key)
        if raw:
            try:
                import json as _json
                vers = _json.loads(raw)
                if vers:
                    _MAVEN_CACHE[artifact_path] = vers
                    return vers
            except Exception:
                pass

    is_neo = 'neoforged' in artifact_path
    # 按实测结果排列候选源（先国内最快的，官方源仅兜底）：
    # - USTC 镜像直接返回不重定向，0.3s；
    # - bmclapi2 的 /maven/ 会 302 到慢节点（实测 7s+），放后面；
    # - 官方源在国内基本超时，只作最后兜底。
    if is_neo:
        urls = [
            (_USTC + '/' + artifact_path + '/maven-metadata.xml', 'xml'),
            (_BMCLAPI + '/maven/' + artifact_path + '/maven-metadata.xml', 'xml'),
            ('https://maven.neoforged.net/releases/' + artifact_path +
             '/maven-metadata.json', 'json'),
        ]
    else:
        urls = [
            (_USTC + '/' + artifact_path + '/maven-metadata.json', 'json'),
            (_BMCLAPI + '/maven/' + artifact_path + '/maven-metadata.json', 'json'),
            (_USTC + '/' + artifact_path + '/maven-metadata.xml', 'xml'),
            ('https://maven.minecraftforge.net/' + artifact_path +
             '/maven-metadata.xml', 'xml'),
        ]

    last = None
    for u, kind in urls:
        try:
            from core.http import get_with_retry
            r = get_with_retry(u, tries=2, timeout=10)
            if kind == 'json':
                data = r.json()
                vers = data.get('versions', []) if isinstance(data, dict) else []
            else:
                import re as _re
                vers = _re.findall(r'<version>([^<]+)</version>', r.text)
            if vers:
                _MAVEN_CACHE[artifact_path] = vers
                if data_root:
                    try:
                        import json as _json
                        meta_cache.put_str(data_root, cache_key, _json.dumps(vers))
                    except Exception:
                        pass
                return vers
            last = Exception('未从 %s 解析出版本' % u)
        except Exception as e:
            last = e
            continue
    raise last if last else Exception('无法获取 Maven 元数据')


def forge_mc_versions(source='bmclapi', data_root=None):
    vers = _maven_versions('net/minecraftforge/forge', source, data_root)
    mc = sorted({v.split('-')[0] for v in vers if '-' in v}, reverse=True)
    return mc


def forge_loader_versions(mc_version, source='bmclapi', data_root=None):
    vers = _maven_versions('net/minecraftforge/forge', source, data_root)
    out = [v for v in vers if v.startswith(mc_version + '-')]
    out.sort(reverse=True)
    return out


def _install_forge(data_root, source, mc_version, loader_version, java_path, log,
                   progress_cb, item_cb, concurrency, segmented):
    # loader_version 形如 1.20.4-49.0.3
    _ensure_base(data_root, source, mc_version, log, progress_cb, item_cb,
                 concurrency, segmented)
    url = rewrite_url(
        'https://maven.minecraftforge.net/net/minecraftforge/forge/%s/'
        'forge-%s-installer.jar' % (loader_version, loader_version), source)
    if log:
        log('下载 Forge 安装器...')
    tmp = tempfile.mkdtemp(prefix='zmc-forge-')
    jar = os.path.join(tmp, 'installer.jar')
    raw = get_bytes(url, fallback=url, tries=3, timeout=120)
    with open(jar, 'wb') as f:
        f.write(raw)
    try:
        _run_installer(jar, data_root, java_path, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    version_id = _detect_installed_version(data_root, 'forge-' + mc_version)
    if not version_id:
        version_id = 'forge-' + loader_version
    if not os.path.isfile(os.path.join(data_root, 'versions', version_id,
                                      version_id + '.json')):
        raise Exception('Forge 安装后未找到版本文件：%s\n'
                        '安装器可能未能正常完成，请重试或手动安装。' % version_id)
    return version_id


# ---------------------------------------------------------------- NeoForge
# NeoForge 版本号前缀 → 原版版本映射（用于把裸的 neo 版本归到 MC 版本下）
_NEO_MAP = {
    '20.1': '1.20.1', '20.2': '1.20.2', '20.3': '1.20.3', '20.4': '1.20.4',
    '20.5': '1.20.5', '20.6': '1.20.6',
    '21.0': '1.21', '21.1': '1.21.1', '21.2': '1.21.2', '21.3': '1.21.3',
    '21.4': '1.21.4', '21.5': '1.21.5', '21.6': '1.21.6',
    '21.7': '1.21.7', '21.8': '1.21.8', '21.9': '1.21.9',
    '21.10': '1.21.10', '21.11': '1.21.11',
    # MC 26.x 起改用「年.月」编号体系
    '26.1': '26.1', '26.2': '26.2', '26.3': '26.3',
}


def neoforge_mc_versions(source='bmclapi', data_root=None):
    vers = _maven_versions('net/neoforged/neoforge', source, data_root)
    mc_set = set()
    for v in vers:
        key = '.'.join(v.split('.')[:2])
        if key in _NEO_MAP:
            mc_set.add(_NEO_MAP[key])
    return sorted(mc_set, reverse=True)


def neoforge_loader_versions(mc_version, source='bmclapi', data_root=None):
    vers = _maven_versions('net/neoforged/neoforge', source, data_root)
    # 反向：mc_version → neo 前缀
    prefix = None
    for k, v in _NEO_MAP.items():
        if v == mc_version:
            prefix = k
            break
    if not prefix:
        return []
    out = [v for v in vers if v.startswith(prefix + '.')]
    out.sort(reverse=True)
    return out


def _install_neoforge(data_root, source, mc_version, loader_version, java_path, log,
                      progress_cb, item_cb, concurrency, segmented):
    # NeoForge 不单独提供原版客户端；安装器会从官方拉取需要的基版本文件，
    # 这里仍先确保原版已安装，避免安装器额外耗时。
    _ensure_base(data_root, source, mc_version, log, progress_cb, item_cb,
                 concurrency, segmented)
    url = rewrite_url(
        'https://maven.neoforged.net/releases/net/neoforged/neoforge/%s/'
        'neoforge-%s-installer.jar' % (loader_version, loader_version), source)
    if log:
        log('下载 NeoForge 安装器...')
    tmp = tempfile.mkdtemp(prefix='zmc-neo-')
    jar = os.path.join(tmp, 'installer.jar')
    raw = get_bytes(url, fallback=url, tries=3, timeout=120)
    with open(jar, 'wb') as f:
        f.write(raw)
    try:
        _run_installer(jar, data_root, java_path, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    version_id = _detect_installed_version(data_root, 'neoforge-' + mc_version)
    if not version_id:
        version_id = 'neoforge-' + loader_version
    if not os.path.isfile(os.path.join(data_root, 'versions', version_id,
                                      version_id + '.json')):
        raise Exception('NeoForge 安装后未找到版本文件：%s\n'
                        '安装器可能未能正常完成，请重试或手动安装。' % version_id)
    return version_id


# ---------------------------------------------------------------- OptiFine
def optifine_mc_versions(source='bmclapi'):
    """OptiFine 官方没有公开 API，BMCLAPI 也没有「全版本列表」接口
    （不带版本的 /optifine 已废弃、返回空数组）。

    这里改为返回一个「常见版本」的探测列表——弹窗真正需要的是
    「当前 MC 版本有没有 OptiFine」，那由 optifine_loader_versions
    直接按版本查询（返回空即表示没有），所以这里只给出一份
    供「支持列表」展示用的参考集合。
    """
    return ['1.21.4', '1.21.1', '1.20.6', '1.20.4', '1.20.2', '1.20.1',
            '1.19.4', '1.19.2', '1.18.2', '1.17.1', '1.16.5', '1.12.2',
            '1.8.9', '1.7.10']


def optifine_loader_versions(mc_version, source='bmclapi'):
    """返回 [(label, value)]，value 为 '类型/补丁号'（如 'HD_U/I7'）。

    数据来源：BMCLAPI /optifine/{mcversion}（国内，实测 0.2s）。
    """
    data = _get_json(_BMCLAPI + '/optifine/%s' % mc_version, source)
    vers = []
    for e in data if isinstance(data, list) else []:
        if e.get('mcversion') != mc_version:
            continue
        patch = e.get('patch') or ''
        typ = e.get('type') or 'HD_U'
        mc = e.get('mcversion') or ''
        vers.append(('%s_%s_%s' % (mc, typ, patch), '%s/%s' % (typ, patch)))
    # 按 patch 字符串倒序（I 越大越新）
    vers.sort(key=lambda x: x[1].split('/')[-1], reverse=True)
    return vers


def _install_optifine(data_root, source, mc_version, loader_version, java_path, log,
                      progress_cb, item_cb, concurrency, segmented):
    """loader_version 形如 'HD_U/I7'（类型/补丁号）。"""
    if log:
        log('下载 OptiFine 安装器（%s / %s）...' % (mc_version, loader_version))
    if '/' in loader_version:
        typ, patch = loader_version.split('/', 1)
    else:
        typ, patch = 'HD_U', loader_version
    # BMCLAPI 的真实下载路径：/optifine/{mcversion}/{type}/{patch}
    url = _BMCLAPI + '/optifine/%s/%s/%s' % (mc_version, typ, patch)
    tmp = tempfile.mkdtemp(prefix='zmc-opti-')
    jar = os.path.join(tmp, 'OptiFine_%s_%s_%s.jar' % (mc_version, typ, patch))
    raw = get_bytes(url, fallback=url, tries=3, timeout=120)
    with open(jar, 'wb') as f:
        f.write(raw)
    try:
        _run_installer(jar, data_root, java_path, log)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    # OptiFine 安装后版本目录形如 optifine_<mc>_<type>_<patch>
    version_id = _detect_installed_version(data_root, 'optifine_' + mc_version)
    if not version_id:
        version_id = 'optifine_%s_%s_%s' % (mc_version, typ, patch)
    if not os.path.isfile(os.path.join(data_root, 'versions', version_id,
                                      version_id + '.json')):
        raise Exception('OptiFine 安装后未找到版本文件：%s\n'
                        'OptiFine 安装器可能不支持无界面安装，'
                        '可改用「Iris」（在实例的「管理光影」里一键安装），'
                        '或手动运行官方安装器后再由本启动器启动。' % version_id)
    return version_id


# ---------------------------------------------------------------- 统一入口
def list_loader_mc_versions(loader_type, source='bmclapi', data_root=None):
    if loader_type == 'fabric':
        return fabric_game_versions(source)
    if loader_type == 'quilt':
        return quilt_game_versions(source)
    if loader_type == 'forge':
        return forge_mc_versions(source, data_root)
    if loader_type == 'neoforge':
        return neoforge_mc_versions(source, data_root)
    if loader_type == 'optifine':
        return optifine_mc_versions(source)
    return []


def list_loader_versions(loader_type, mc_version, source='bmclapi', data_root=None):
    """返回 [(label, value), ...]，label 用于展示，value 用于安装。"""
    if loader_type == 'fabric':
        return [(v, v) for v in fabric_loader_versions(mc_version, source)]
    if loader_type == 'quilt':
        return [(v, v) for v in quilt_loader_versions(mc_version, source)]
    if loader_type == 'forge':
        return [(v, v) for v in forge_loader_versions(mc_version, source, data_root)]
    if loader_type == 'neoforge':
        return [(v, v) for v in neoforge_loader_versions(mc_version, source, data_root)]
    if loader_type == 'optifine':
        return optifine_loader_versions(mc_version, source)
    return []


# ---------------------------------------------------------------- 弹窗用：并发 + 缓存
def query_loader_support(data_root, loader_types, mc_version, source='bmclapi'):
    """并发查询多个加载器对指定 MC 版本的支持情况与可用版本。

    返回 {loader_type: (supported, [(label, value), ...])}。
    - 优先读本地缓存（6 小时 TTL），命中则完全不走网络；
    - 未命中的才联网，且各加载器之间并发查询，不再一个接一个等。
    """
    from concurrent.futures import ThreadPoolExecutor
    from core import meta_cache

    result = {}
    pending = []
    for code in loader_types:
        key = 'sup|%s|%s|%s' % (code, mc_version, source)
        cached = meta_cache.get(data_root, key)
        if cached is not None:
            try:
                supported, vers = cached
                result[code] = (bool(supported), [tuple(v) for v in vers])
                continue
            except Exception:
                pass
        pending.append(code)

    if not pending:
        return result

    def one(code):
        supported = False
        vers = []
        try:
            if code == 'optifine':
                # OptiFine 没有「全版本列表」接口，直接按当前版本查更省一次请求
                vers = optifine_loader_versions(mc_version, source)
                supported = bool(vers)
            else:
                mcs = list_loader_mc_versions(code, source, data_root)
                supported = mc_version in mcs
                if supported:
                    vers = list_loader_versions(code, mc_version, source, data_root)
        except Exception:
            supported = False
            vers = []
        return code, supported, vers

    workers = min(5, len(pending))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for code, supported, vers in ex.map(one, pending):
            result[code] = (supported, vers)
            try:
                meta_cache.put(data_root, 'sup|%s|%s|%s' % (code, mc_version, source),
                               [supported, [list(v) for v in vers]])
            except Exception:
                pass
    return result


def install_loader(data_root, source, loader_type, mc_version, loader_version,
                   java_path='java', log=None, progress_cb=None, item_cb=None,
                   concurrency=16, segmented=True):
    if loader_type == 'fabric':
        return _install_fabric(data_root, source, mc_version, loader_version, log,
                              progress_cb, item_cb, concurrency, segmented)
    if loader_type == 'quilt':
        return _install_quilt(data_root, source, mc_version, loader_version, log,
                             progress_cb, item_cb, concurrency, segmented)
    if loader_type == 'forge':
        return _install_forge(data_root, source, mc_version, loader_version, java_path,
                             log, progress_cb, item_cb, concurrency, segmented)
    if loader_type == 'neoforge':
        return _install_neoforge(data_root, source, mc_version, loader_version,
                               java_path, log, progress_cb, item_cb,
                               concurrency, segmented)
    if loader_type == 'optifine':
        return _install_optifine(data_root, source, mc_version, loader_version,
                               java_path, log, progress_cb, item_cb,
                               concurrency, segmented)
    raise Exception('不支持的加载器类型：%s' % loader_type)


def suggest_instance_name(loader_type, mc_version, loader_version):
    names = {
        'fabric': 'Fabric', 'quilt': 'Quilt', 'forge': 'Forge',
        'neoforge': 'NeoForge', 'optifine': 'OptiFine',
    }
    prefix = names.get(loader_type, loader_type.title())
    return '%s %s' % (prefix, mc_version)
