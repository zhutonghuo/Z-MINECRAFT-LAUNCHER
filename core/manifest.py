import json
import os

from core.config import rewrite_url
from core.http import get_json, make_session, UA

MANIFEST_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest.json'


def get_manifest(source='bmclapi', cached_path=None):
    if cached_path and os.path.isfile(cached_path):
        try:
            with open(cached_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # 依次尝试：当前源 -> 其余镜像 -> 官方 -> 官方(强制不走系统代理兜底)
    order = []
    if source and source != 'official':
        order.append(source)
    for s in ('bmclapi', 'mcbbs'):
        if s not in order:
            order.append(s)
    order.append('official')
    last_err = None
    for s in order:
        try:
            return get_json(rewrite_url(MANIFEST_URL, s), tries=2, timeout=20)
        except Exception as e:
            last_err = e
    # 最后兜底：官方源且强制禁用系统/自定义代理，防止本机代理把请求拦死
    try:
        sess = make_session(pool=4)
        sess.trust_env = False
        sess.proxies = {}
        return sess.get(MANIFEST_URL, timeout=20, headers=UA).json()
    except Exception as e:
        last_err = e
    raise last_err


def categorize(manifest):
    rel, snap, old = [], [], []
    for v in manifest.get('versions', []):
        t = v.get('type')
        if t == 'release':
            rel.append(v)
        elif t == 'snapshot':
            snap.append(v)
        else:
            old.append(v)
    return rel, snap, old, manifest.get('latest', {})
