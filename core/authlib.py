# -*- coding: utf-8 -*-
"""authlib-injector 支持。

第三方 Yggdrasil 登录服务器（如各类皮肤站/私服）要求客户端在启动时注入
authlib-injector，并把 API 根地址传给游戏。本模块负责：
  1. 首次使用时自动下载 authlib-injector jar
  2. 生成 -javaagent 启动参数
若下载失败，会退回「不注入」模式并给出提示（部分服务器仍可正常启动）。
"""
import os

from core.http import get_bytes

# 官方构建地址（Authlib-Injector 官方发布）
INJECTOR_VERSION = '1.2.8'
MIRRORS = [
    # 官方镜像站（最快）
    'https://authlib-injector.yushi.moe/artifact/latest/authlib-injector.jar',
    'https://authlib-injector.yushi.moe/artifact/55/authlib-injector-1.2.8.jar',
    # GitHub 正式发布页
    'https://github.com/yushijinhun/authlib-injector/releases/latest/download/'
    'authlib-injector-%s.jar' % INJECTOR_VERSION,
    # 国内代理
    'https://gh-proxy.com/https://github.com/yushijinhun/authlib-injector/'
    'releases/latest/download/authlib-injector-%s.jar' % INJECTOR_VERSION,
    'https://mirror.ghproxy.com/https://github.com/yushijinhun/authlib-injector/'
    'releases/latest/download/authlib-injector-%s.jar' % INJECTOR_VERSION,
]


def injector_path(data_root):
    return os.path.join(data_root, 'authlib-injector.jar')


def ensure_injector(data_root):
    """确保本地有 authlib-injector jar，缺少则下载。返回路径或 None"""
    p = injector_path(data_root)
    if os.path.isfile(p) and os.path.getsize(p) > 10000:
        return p
    os.makedirs(data_root, exist_ok=True)
    last_err = None
    for url in MIRRORS:
        try:
            data = get_bytes(url, tries=2, timeout=60)
            if data and len(data) > 10000:
                with open(p, 'wb') as f:
                    f.write(data)
                return p
            last_err = '下载内容为空或过小'
        except Exception as e:
            last_err = str(e)
    # 下载失败时不要留下半个损坏的 jar，否则下次会误判为“已就绪”
    try:
        if os.path.isfile(p):
            os.remove(p)
    except Exception:
        pass
    _LAST_ERROR['msg'] = last_err or '未知错误'
    return None


# 记录注入器下载失败原因，供启动流程给出可读提示
_LAST_ERROR = {'msg': ''}


def javaagent_arg(data_root, server):
    """生成 -javaagent 参数（authlib-injector 需要 API 根地址）

    第三方账号必须注入 authlib-injector，否则游戏会拿第三方 token 去
    Mojang 官方服务器校验 → 401 未授权 → 游戏掉进“试玩”界面。
    因此这里失败时直接抛出异常，不再静默返回空列表。
    """
    p = ensure_injector(data_root)
    if not p:
        raise Exception(
            '第三方登录需要 authlib-injector 组件，但下载失败（%s）。\n'
            '请检查网络/代理后重试，或在“设置”里切换下载源。'
            % (_LAST_ERROR.get('msg') or '未知错误'))
    api = server.rstrip('/')
    return ['-javaagent:%s=%s' % (p, api)]
