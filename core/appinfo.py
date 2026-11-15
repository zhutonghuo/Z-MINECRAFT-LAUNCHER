# -*- coding: utf-8 -*-
"""启动器自身版本与「检查更新」相关的常量与工具。

把版本号集中到这一处，避免散落在多处（之前 launcher_version 只硬编码在
build_command 里）。官网静态托管的 version.json 也由这里给出地址。
"""
import re

# 当前启动器版本（与官网 version.json 里的 latest 比较）
LAUNCHER_VERSION = '2.0.0'

# 服务器上的版本信息 JSON（官网静态托管，HTTP 直连即可）
VERSION_INFO_URL = 'http://47.95.246.166/zml/version.json'


def parse_version(v):
    """把 '1.5.2' / 'v1.5.2' / '1.5.2-beta' 解析成可比较的 int 元组。

    非数字段按 0 计，前缀 v/V 自动忽略，分隔符支持 . 和 -。
    """
    if not v:
        return (0,)
    s = str(v).lstrip('vV')
    parts = re.split(r'[.\-]', s)
    out = []
    for p in parts:
        m = re.match(r'\d+', p)
        out.append(int(m.group()) if m else 0)
    return tuple(out) if out else (0,)


def compare_versions(a, b):
    """返回 -1 / 0 / 1：a 比 b 旧 / 相同 / 更新。"""
    pa, pb = parse_version(a), parse_version(b)
    n = max(len(pa), len(pb))
    pa = pa + (0,) * (n - len(pa))
    pb = pb + (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def is_newer(remote, local):
    """远端版本是否比本地新（用于判断是否有更新）。"""
    return compare_versions(remote, local) > 0
