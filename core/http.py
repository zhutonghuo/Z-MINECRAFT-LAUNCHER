# -*- coding: utf-8 -*-
"""带重试与镜像降级的 HTTP 层。

背景：BMCLAPI / MCBBS 等镜像会把请求 302 到多个第三方节点，
这些节点在并发高时经常直接断连（ConnectionResetError 10054）或 SSL 失败。
本模块提供：
  1. 复用的 Session（连接池 + urllib3 自动重试）
  2. 显式重试 + 指数退避（针对断连类瞬时错误）
  3. 镜像失败自动降级到官方源（fallback）
  4. 中文友好错误信息
"""
import threading
import time

import requests
from requests.adapters import HTTPAdapter

UA = {'User-Agent': 'ZMC-Launcher/1.0'}

# 全局代理设置：None=跟随系统，''=不使用代理，其它=代理地址
_PROXY = {'value': None}
_PROXY_VER = 0


def set_proxy(value):
    """设置全局代理。value 为 None 时跟随系统环境变量，'' 表示禁用代理"""
    global _PROXY_VER
    _PROXY['value'] = value
    _PROXY_VER += 1
    # 通知下载层重建各线程的 Session
    try:
        from core import download as _dl
        _dl.sync_proxy_version(_PROXY_VER)
    except Exception:
        pass
    # 换代理后镜像状态需重新评估
    try:
        reset_circuit()
    except Exception:
        pass


def get_proxy():
    return _PROXY['value']

# 断连 / 超时 / SSL 等瞬时错误（可重试）
TRANSIENT = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.SSLError,
    requests.exceptions.ContentDecodingError,
)

# HTTP 状态码（可重试）
RETRY_STATUS = (408, 425, 429, 500, 502, 503, 504)


def is_transient(exc):
    """判断是否为可重试的瞬时错误。

    包含：连接重置/拒绝/超时、SSL 失败、连接中断，
    以及镜像节点常见的 502/503/504（上游节点挂了，换节点重试有救）。
    """
    if isinstance(exc, TRANSIENT):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        code = getattr(exc.response, 'status_code', None)
        return code in (502, 503, 504)
    return False


def make_session(pool=32, retries=3, backoff=0.4):
    """创建带连接池与自动重试的 Session"""
    try:
        from urllib3.util.retry import Retry
        retry = Retry(total=retries, connect=retries, read=retries,
                      status=retries, backoff_factor=backoff,
                      status_forcelist=RETRY_STATUS,
                      allowed_methods=frozenset(['GET', 'HEAD']),
                      raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=pool,
                              pool_maxsize=pool)
    except Exception:
        adapter = HTTPAdapter(pool_connections=pool, pool_maxsize=pool)
    s = requests.Session()
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    s.headers.update(UA)
    # 代理设置：'' 禁用；None 跟随系统；其它为自定义地址
    px = _PROXY['value']
    if px == '':
        s.trust_env = False
        s.proxies = {}
    elif px:
        s.proxies = {'http': px, 'https': px}
    return s


def friendly_error(exc):
    """把底层异常翻译成用户能看懂的中文"""
    text = str(exc)
    if isinstance(exc, requests.exceptions.SSLError) or 'SSL' in text:
        return '镜像节点 SSL 握手失败（该节点可能已不可用）'
    if 'ConnectionResetError' in text or '10054' in text:
        return '镜像节点强制断开了连接'
    if 'Connection aborted' in text:
        return '镜像节点中断了连接'
    if 'Connection refused' in text:
        return '镜像节点拒绝连接'
    if 'Read timed out' in text or 'timeout' in text.lower():
        return '连接超时'
    if 'RemoteDisconnected' in text:
        return '镜像节点未正常响应就断开了'
    if isinstance(exc, requests.exceptions.HTTPError):
        return '服务器返回 HTTP %s' % (getattr(exc.response, 'status_code', '错误'))
    return text.split('(')[0].strip() or text


def get_with_retry(url, tries=4, timeout=30, backoff=0.6, session=None, params=None):
    """GET 并对瞬时错误重试；仍失败则抛出最后一个异常"""
    sess = session or make_session(pool=8)
    own = session is None
    last = None
    try:
        for i in range(tries):
            try:
                r = sess.get(url, timeout=timeout, headers=UA, params=params)
                if r.status_code in RETRY_STATUS:
                    raise requests.exceptions.HTTPError(
                        'HTTP %d' % r.status_code, response=r)
                r.raise_for_status()
                return r
            except TRANSIENT as e:
                last = e
            except requests.exceptions.HTTPError as e:
                code = getattr(e.response, 'status_code', None)
                if code in RETRY_STATUS:
                    last = e
                else:
                    raise
            if i < tries - 1:
                time.sleep(min(backoff * (2 ** i), 5.0))
        raise last
    finally:
        if own:
            try:
                sess.close()
            except Exception:
                pass


def get_bytes(url, tries=4, timeout=30, fallback=None, session=None, backoff=0.6):
    """取字节内容；镜像失败时自动降级到 fallback（官方源）"""
    try:
        return get_with_retry(url, tries=tries, timeout=timeout,
                              session=session, backoff=backoff).content
    except Exception as e:
        if fallback and fallback != url:
            # 官方源用更少的重试次数，快速接管
            try:
                return get_with_retry(fallback, tries=max(2, tries // 2),
                                      timeout=timeout, session=session,
                                      backoff=backoff).content
            except Exception:
                raise e
        raise


def get_json(url, tries=4, timeout=30, fallback=None, session=None, backoff=0.6):
    """取 JSON；镜像失败时自动降级到 fallback（官方源）"""
    try:
        return get_with_retry(url, tries=tries, timeout=timeout,
                              session=session, backoff=backoff).json()
    except Exception as e:
        if fallback and fallback != url:
            try:
                return get_with_retry(fallback, tries=max(2, tries // 2),
                                      timeout=timeout, session=session,
                                      backoff=backoff).json()
            except Exception:
                raise e
        raise


# ---------------------------------------------------------------- 镜像健康熔断
# BMCLAPI / MCBBS 会把请求 302 到多个第三方节点，其中部分节点常年挂起或断连。
# 连续失败达到阈值后，把镜像源标记为不可用，后续任务直接走官方源，
# 避免每个文件都去撞一次坏节点（那会让安装慢到无法忍受）。
_CIRCUIT = {'fails': 0, 'open_until': 0.0, 'threshold': 3, 'cool': 120.0}
_CIRCUIT_LOCK = threading.Lock()


def report_failure():
    """记录一次镜像失败；若达到阈值则打开熔断，返回 True"""
    with _CIRCUIT_LOCK:
        _CIRCUIT['fails'] += 1
        if _CIRCUIT['fails'] >= _CIRCUIT['threshold']:
            _CIRCUIT['open_until'] = time.time() + _CIRCUIT['cool']
            _CIRCUIT['fails'] = 0
            return True
    return False


def report_success():
    with _CIRCUIT_LOCK:
        _CIRCUIT['fails'] = 0


def circuit_open():
    """熔断是否打开（镜像当前不可用，应直接走官方源）"""
    with _CIRCUIT_LOCK:
        return time.time() < _CIRCUIT['open_until']


def circuit_state():
    with _CIRCUIT_LOCK:
        remain = max(0, int(_CIRCUIT['open_until'] - time.time()))
        return {'fails': _CIRCUIT['fails'], 'open': remain > 0, 'remain': remain}


def reset_circuit():
    """重置熔断状态（切换镜像源后调用）"""
    with _CIRCUIT_LOCK:
        _CIRCUIT['fails'] = 0
        _CIRCUIT['open_until'] = 0.0
