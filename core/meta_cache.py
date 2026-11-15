# -*- coding: utf-8 -*-
"""加载器元数据的本地缓存。

「选择要安装的加载器」弹窗需要查 5 个加载器的元数据（Fabric / Quilt /
Forge / NeoForge / OptiFine）。即使全部走国内镜像，也要多次网络往返；
而这些数据变化极慢（加载器一天可能才更新一两次）。

所以缓存到本地 JSON，带 TTL：
- 缓存有效 → 直接读盘，弹窗秒开，零网络请求；
- 缓存过期或损坏 → 重新联网获取并回写。

缓存文件放在 data_root/cache/loader_meta.json，随启动器数据目录一起迁移。
"""
import json
import os
import threading
import time

CACHE_TTL = 6 * 3600          # 6 小时
_CACHE_VERSION = 2             # 结构变化时 +1，旧缓存自动失效
_LOCK = threading.Lock()


def _cache_path(data_root):
    d = os.path.join(data_root, 'cache')
    return os.path.join(d, 'loader_meta.json')


def _read(data_root):
    """读取缓存，返回 {key: (timestamp, value)} 或 {}"""
    p = _cache_path(data_root)
    try:
        with open(p, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get('_v') != _CACHE_VERSION:
        return {}
    items = data.get('items')
    return items if isinstance(items, dict) else {}


def _write(data_root, items):
    p = _cache_path(data_root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'_v': _CACHE_VERSION, 'items': items}, f,
                      ensure_ascii=False)
        os.replace(tmp, p)
    except Exception:
        pass


def get(data_root, key):
    """取缓存值；没有或已过期返回 None"""
    if not data_root:
        return None
    with _LOCK:
        items = _read(data_root)
    ent = items.get(key)
    if not isinstance(ent, (list, tuple)) or len(ent) != 2:
        return None
    ts, val = ent
    if not isinstance(ts, (int, float)) or (time.time() - ts) > CACHE_TTL:
        return None
    return val


def put(data_root, key, value):
    """写入缓存"""
    if not data_root:
        return
    with _LOCK:
        items = _read(data_root)
        items[key] = (time.time(), value)
        _write(data_root, items)


def get_str(data_root, key):
    """取字符串类缓存（Maven 元数据很大，必须落盘才划算）"""
    v = get(data_root, key)
    return v if isinstance(v, str) else None


def put_str(data_root, key, value):
    if isinstance(value, str):
        put(data_root, key, value)


def clear(data_root):
    if not data_root:
        return
    with _LOCK:
        _write(data_root, {})
