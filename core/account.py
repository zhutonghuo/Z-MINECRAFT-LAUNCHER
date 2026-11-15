# -*- coding: utf-8 -*-
"""账号刷新：正版（微软）与第三方（Yggdrasil）统一入口。

「同步延迟大」的根本原因是 accessToken 有有效期，且角色资料（皮肤/披风）
不会自动更新。本模块提供主动刷新的能力：
  - 微软账号：用 refresh_token 换新令牌并重拉角色资料
  - 第三方账号：用 authserver/refresh 换新令牌并重拉角色资料
"""
from core.auth import microsoft_refresh, ygg_refresh


def refresh_account(acc, client_id=None):
    """刷新任意类型账号，返回更新后的账号字典"""
    t = acc.get('type')
    if t == 'microsoft':
        from core.auth import CLIENT_ID
        return microsoft_refresh(acc, client_id or CLIENT_ID)
    if t == 'yggdrasil':
        server = acc.get('server')
        if not server:
            raise Exception('账号缺少登录服务器地址，无法刷新')
        return ygg_refresh(server, acc)
    # 离线账号无需刷新
    return dict(acc)


def account_expired(acc):
    """判断账号令牌是否已过期。

    微软账号的 accessToken 有效期只有 1 小时左右（登录响应里的 expiresIn），
    若沿用固定的 20 小时阈值，令牌早已失效却不会刷新，
    表现就是进游戏被判定未授权而落到“试玩”界面。
    因此优先按 expiresIn + obtainedAt 精确计算，缺失时才退回保守估计。
    """
    got = acc.get('obtainedAt')
    if not got:
        return True
    import time
    now_ms = time.time() * 1000
    expires_in = acc.get('expiresIn')
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        # 提前 5 分钟刷新，避免临界点失效
        return now_ms > got + max(0, (expires_in - 300) * 1000)
    age_h = (now_ms - got) / 3600000.0
    return age_h > 20          # 缺少 expiresIn 时的保守估计


def token_valid(acc):
    """实际探测令牌是否仍然可用（联网校验，返回 True/False）。

    微软账号的 expiresIn 只反映 OAuth 令牌寿命，与 MC 签发的 accessToken
    有效期并不完全一致；而 MC 的 accessToken 过期后，游戏会判定未授权，
    表现就是进入“试玩”界面。因此启动前做一次真实校验最保险。
    离线账号不需要网络，直接视为有效。
    """
    t = acc.get('type')
    if t == 'offline':
        return True
    try:
        if t == 'microsoft':
            from core.auth import mc_profile
            mc_profile(acc.get('accessToken') or '')
            return True
        if t == 'yggdrasil':
            server = acc.get('server')
            if not server:
                return False
            from core.auth import _get_json
            _get_json(server.rstrip('/') + '/minecraft/profile',
                      {'Authorization': 'Bearer ' + (acc.get('accessToken') or '')})
            return True
    except Exception:
        return False
    return True


def ensure_fresh(acc, client_id=None):
    """确保账号令牌可用：先按时间判断，必要时刷新，再做一次联网校验。

    返回 (是否可用, 新账号字典或 None, 中文说明)
    """
    t = acc.get('type')
    if t == 'offline':
        return True, acc, '离线账号无需验证'
    if t not in ('microsoft', 'yggdrasil'):
        return True, acc, ''
    # 1) 时间上已过期 → 先刷新
    if account_expired(acc):
        try:
            new = refresh_account(acc, client_id)
            return True, new, '令牌已过期，已自动刷新'
        except Exception as e:
            # 刷新失败还有救：老令牌可能仍然有效，继续用但要如实告知
            if token_valid(acc):
                return True, acc, '令牌刷新失败（%s），但当前令牌仍可用' % str(e)[:120]
            return False, None, '令牌已过期且刷新失败：%s' % str(e)[:200]

    # 2) 时间上没过期 → 联网探活，防止 expiresIn 不可靠
    if token_valid(acc):
        return True, acc, '令牌有效'
    try:
        new = refresh_account(acc, client_id)
        if token_valid(new):
            return True, new, '检测到令牌已失效，已自动刷新'
        return False, None, '刷新后令牌仍无法通过校验，请重新登录该账号'
    except Exception as e:
        return False, None, '令牌已失效且刷新失败：%s' % str(e)[:200]


def account_label(acc):
    """账号显示名（区分登录来源）"""
    name = acc.get('name') or '未知'
    t = acc.get('type')
    if t == 'microsoft':
        return name + '（正版）'
    if t == 'yggdrasil':
        srv = acc.get('server') or ''
        host = srv.split('//')[-1].split('/')[0]
        return name + ('（%s）' % host if host else '（第三方）')
    return name + '（离线）'
