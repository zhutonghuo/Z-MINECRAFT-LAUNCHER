import json
import os
import platform
import re

from core.config import rewrite_url

OS_NAME = 'windows'
OS_ARCH = 'x86_64' if platform.machine().lower() in ('amd64', 'x86_64') else (
    'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x86')


def read_version_json(data_root, version_id):
    p = os.path.join(data_root, 'versions', version_id, version_id + '.json')
    if os.path.isfile(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def resolve_chain(data_root, version_id):
    chain = []
    cur = version_id
    guard = 0
    while cur and guard < 50:
        vj = read_version_json(data_root, cur)
        if not vj:
            break
        chain.insert(0, vj)
        cur = vj.get('inheritsFrom')
        guard += 1
    return chain


def merge_version(data_root, version_id):
    chain = resolve_chain(data_root, version_id)
    if not chain:
        return None
    merged = {
        'id': version_id,
        'mainClass': None,
        'minecraftArguments': '',
        'arguments': {'game': [], 'jvm': []},
        'libraries': [],
        'assetIndex': None,
        'assets': None,
        'javaVersion': None,
    }
    for vj in chain:
        if vj.get('mainClass'):
            merged['mainClass'] = vj['mainClass']
        if vj.get('minecraftArguments'):
            merged['minecraftArguments'] = vj['minecraftArguments']
        if vj.get('arguments'):
            merged['arguments']['game'] += vj['arguments'].get('game', [])
            merged['arguments']['jvm'] += vj['arguments'].get('jvm', [])
        if vj.get('libraries'):
            merged['libraries'] += vj['libraries']
        if vj.get('assetIndex'):
            merged['assetIndex'] = vj['assetIndex']
        if vj.get('assets'):
            merged['assets'] = vj['assets']
        if vj.get('javaVersion'):
            merged['javaVersion'] = vj['javaVersion']
    return merged


def rule_allowed(rules, features=None):
    features = features or {}
    allowed = False
    for rule in rules:
        action = rule.get('action', 'allow')
        ok = True
        os_rule = rule.get('os')
        if os_rule:
            if os_rule.get('name') and os_rule['name'] != OS_NAME:
                ok = False
            if ok and os_rule.get('arch') and os_rule['arch'] != OS_ARCH:
                ok = False
        feat_rule = rule.get('features')
        if feat_rule:
            for k, v in feat_rule.items():
                if features.get(k) != v:
                    ok = False
                    break
        if ok:
            allowed = (action == 'allow')
    return allowed


def lib_allowed(lib, features=None):
    rules = lib.get('rules')
    if not rules:
        return True
    return rule_allowed(rules, features)


def maven_path(name):
    parts = name.split(':')
    group, artifact, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else None
    g = group.replace('.', '/')
    fn = artifact + '-' + version + ('-' + classifier if classifier else '') + '.jar'
    return f"{g}/{artifact}/{version}/{fn}"


def native_classifier(lib):
    natives = lib.get('natives')
    if not natives:
        return None
    cl = natives.get('windows')
    if not cl:
        return None
    arch = 'x86_64' if OS_ARCH == 'x86_64' else 'arm64'
    return cl.replace('${arch}', arch)


def subst(text, token_map):
    import re
    return re.sub(r'\$\{([^}]+)\}', lambda m: str(token_map.get(m.group(1), m.group(0))), text)


def collect_downloads(data_root, source, merged, version_id):
    tasks = []

    def add(url, dest, sha1=None, size=None, extra=None):
        """登记下载任务，同时保留官方源地址作为镜像失败时的兜底"""
        t = {'url': rewrite_url(url, source), 'fallback': url,
             'dest': dest, 'sha1': sha1, 'size': size}
        if extra:
            t.update(extra)
        tasks.append(t)

    chain = resolve_chain(data_root, version_id)
    base = None
    for vj in chain:
        if vj.get('downloads', {}).get('client'):
            base = vj
            break
    if base:
        c = base['downloads']['client']
        dest = os.path.join(data_root, 'versions', version_id, version_id + '.jar')
        add(c['url'], dest, c.get('sha1'), c.get('size'))
    lib_dir = os.path.join(data_root, 'libraries')
    for lib in merged['libraries']:
        if not lib_allowed(lib):
            continue
        if lib.get('downloads', {}).get('artifact'):
            a = lib['downloads']['artifact']
            add(a['url'], os.path.join(lib_dir, a['path']), a.get('sha1'), a.get('size'))
        elif lib.get('name'):
            path = maven_path(lib['name'])
            baseurl = lib.get('url') or 'https://libraries.minecraft.net/'
            add(baseurl + path, os.path.join(lib_dir, path))
        cl = native_classifier(lib)
        if cl:
            classifiers = lib.get('downloads', {}).get('classifiers', {})
            if classifiers.get(cl):
                cj = classifiers[cl]
                dest = os.path.join(data_root, 'versions', version_id, 'natives',
                                    os.path.basename(cj['path']))
                add(cj['url'], dest, cj.get('sha1'), cj.get('size'), {'native': True})
            elif lib.get('name'):
                path = maven_path(lib['name'] + ':' + cl)
                baseurl = lib.get('url') or 'https://libraries.minecraft.net/'
                dest = os.path.join(data_root, 'versions', version_id, 'natives',
                                    os.path.basename(path))
                add(baseurl + path, dest, None, None, {'native': True})
    if merged.get('assetIndex'):
        ai = merged['assetIndex']
        dest = os.path.join(data_root, 'assets', 'indexes', ai['id'] + '.json')
        add(ai['url'], dest, ai.get('sha1'), ai.get('size'))
    return tasks


def collect_assets(data_root, source, merged):
    ai = merged.get('assetIndex')
    if not ai:
        return []
    idx_path = os.path.join(data_root, 'assets', 'indexes', ai['id'] + '.json')
    if not os.path.isfile(idx_path):
        return []
    with open(idx_path, 'r', encoding='utf-8') as f:
        index = json.load(f)
    tasks = []
    for o in index.get('objects', {}).values():
        h = o['hash']
        url = 'https://resources.download.minecraft.net/' + h[:2] + '/' + h
        dest = os.path.join(data_root, 'assets', 'objects', h[:2], h)
        tasks.append({'url': rewrite_url(url, source), 'fallback': url,
                      'dest': dest, 'sha1': h, 'size': o.get('size')})
    return tasks


def eval_args(args, token_map, features=None):
    out = []
    for a in args:
        if isinstance(a, str):
            out.append(subst(a, token_map))
            continue
        if isinstance(a, dict):
            rules = a.get('rules')
            if rules is not None and not rule_allowed(rules, features):
                continue
            val = a.get('value')
            if isinstance(val, list):
                out.extend(subst(v, token_map) for v in val)
            elif isinstance(val, str):
                out.append(subst(val, token_map))
    return out


def _set_option(text, key, value):
    """在 options.txt 文本里设置某个键，返回 (新文本, 是否发生改动)。

    保留用户其余设置不变；若该键不存在则追加。
    """
    pat = re.compile(r'(?m)^%s:.*$' % re.escape(key))
    if pat.search(text):
        new_text = pat.sub('%s:%s' % (key, value), text)
        return new_text, new_text != text
    text = text.rstrip('\n')
    if text:
        text += '\n'
    return text + '%s:%s\n' % (key, value), True


def missing_language_assets(data_root, merged, lang):
    """检查指定语言的资源是否已下载到本地，返回缺失的对象名列表。

    语言包缺失时游戏会静默回退成英文，用户容易一头雾水，
    所以启动前先查一遍并给出提示。
    """
    if not lang:
        return []
    ai = merged.get('assetIndex')
    if not ai:
        return []
    idx_path = os.path.join(data_root, 'assets', 'indexes', ai['id'] + '.json')
    if not os.path.isfile(idx_path):
        return []
    try:
        with open(idx_path, 'r', encoding='utf-8') as f:
            index = json.load(f)
    except Exception:
        return []
    objs = index.get('objects', {})
    missing = []
    for name, meta in objs.items():
        if not name.startswith('minecraft/lang/'):
            continue
        # zh_cn 只需 zh_cn 本身；zh_tw 需要 zh_tw 与 zh_hk/zh_hant 之类，按前缀匹配近似
        base = name[len('minecraft/lang/'):-len('.json')]
        if base != lang and not base.startswith(lang + '_'):
            continue
        h = meta.get('hash')
        if not h:
            continue
        p = os.path.join(data_root, 'assets', 'objects', h[:2], h)
        if not os.path.isfile(p):
            missing.append(name)
    return missing


def apply_instance_options(game_dir, lang='zh_cn', skip_onboard=True):
    """为实例预置游戏选项：中文（简体）+ 跳过首次启动引导页。

    新建实例的 options.txt 是全新的，没有 lang 键 → 游戏默认英语；
    也没有 onboardAccessibility 键 → 会弹「Welcome to Minecraft!」向导。
    这里在启动前把两者写好，用户打开就是中文界面、直接进主菜单。

    lang 为空字符串时不改语言（跟随游戏自身设置）。
    返回实际改动的项列表（空列表表示无需改动）。
    """
    if not game_dir:
        return []
    p = os.path.join(game_dir, 'options.txt')
    changed = []
    try:
        os.makedirs(game_dir, exist_ok=True)
        if os.path.isfile(p):
            with open(p, 'r', encoding='utf-8') as f:
                text = f.read()
        else:
            text = 'version:5023\n'
        if lang:
            text, c = _set_option(text, 'lang', lang)
            if c:
                changed.append('lang=' + lang)
        if skip_onboard:
            text, c = _set_option(text, 'onboardAccessibility', 'false')
            if c:
                changed.append('onboardAccessibility=false')
        if changed:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(text)
        return changed
    except Exception:
        return []


def skip_onboarding(game_dir):
    """兼容旧调用：仅跳过首次启动引导页。"""
    return bool(apply_instance_options(game_dir, lang='', skip_onboard=True))


from core.appinfo import LAUNCHER_VERSION


def build_command(data_root, merged, account, instance, java_path, settings):
    version_id = merged['id']
    game_dir = instance['gameDir']
    assets_root = os.path.join(data_root, 'assets')
    assets_index = merged.get('assets') or (merged.get('assetIndex') or {}).get('id')
    natives_dir = os.path.join(data_root, 'versions', version_id, 'natives')
    libs_dir = os.path.join(data_root, 'libraries')
    cp = []
    for lib in merged['libraries']:
        if not lib_allowed(lib):
            continue
        if lib.get('downloads', {}).get('artifact'):
            cp.append(os.path.join(libs_dir, lib['downloads']['artifact']['path']))
        elif lib.get('name'):
            cp.append(os.path.join(libs_dir, maven_path(lib['name'])))
    cp.append(os.path.join(data_root, 'versions', version_id, version_id + '.jar'))
    # 第三方登录服务器：auth_session 必须为空，验证交给 authlib-injector
    is_ygg = account.get('type') == 'yggdrasil'
    token_map = {
        'auth_player_name': account['name'],
        'version_name': version_id,
        'game_directory': game_dir,
        'assets_root': assets_root,
        'assets_index_name': assets_index,
        'auth_uuid': account['uuid'],
        'auth_access_token': account['accessToken'],
        'auth_session': '' if is_ygg else account['accessToken'],
        'user_type': account.get('userType', 'mojang'),
        'user_properties': account.get('userProperties', '[]'),
        'version_type': 'MCL',
        'clientid': '',
        'auth_xuid': account.get('xuid', ''),
        'launcher_name': 'MinecraftLauncher',
        'launcher_version': LAUNCHER_VERSION,
        'natives_directory': natives_dir,
        'library_directory': libs_dir,
        'classpath_separator': ';',
        'classpath': ';'.join(cp),
    }
    jvm = ['-Xmx%dM' % settings['maxMemory'], '-Xms%dM' % settings['minMemory']]
    if merged.get('arguments', {}).get('jvm'):
        jvm += eval_args(merged['arguments']['jvm'], token_map)
    else:
        jvm += ['-XX:+UseConcMarkSweepGC', '-XX:+CMSIncrementalMode',
                '-XX:-UseAdaptiveSizePolicy', '-Xmn128M',
                '-Djava.library.path=${natives_directory}', '-cp', '${classpath}']
    game = []
    if merged.get('arguments', {}).get('game'):
        game += eval_args(merged['arguments']['game'], token_map)
    elif merged.get('minecraftArguments'):
        game += merged['minecraftArguments'].split(' ')
    jvm = [subst(x, token_map) for x in jvm]
    game = [subst(x, token_map) for x in game]
    if instance.get('javaArgs'):
        jvm += instance['javaArgs'].split()
    if settings.get('javaArgs'):
        jvm += settings['javaArgs'].split()
    if instance.get('gameArgs'):
        game += instance['gameArgs'].split()
    if settings.get('gameArgs'):
        game += settings['gameArgs'].split()
    # 第三方登录服务器账号需要注入 authlib-injector，并去掉 auth_session
    if account.get('type') == 'yggdrasil' and account.get('server'):
        from core.authlib import javaagent_arg
        # 注入失败必须报错：没有注入器时第三方 token 会被送去 Mojang 校验，
        # 结果是 401 未授权 → 游戏掉进“试玩”界面（静默忽略只会让用户一头雾水）
        jvm += javaagent_arg(data_root, account['server'])
    cmd = [java_path] + jvm + [merged['mainClass']] + game
    return cmd, natives_dir
