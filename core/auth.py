import hashlib
import json
import os
import time
import uuid

import requests

CLIENT_ID = 'c36a9fb6-4f2a-41ff-90bd-ae7cc92031eb'
SCOPE = 'XboxLive.signin offline_access'
UA = {'User-Agent': 'MinecraftLauncher/1.0', 'Content-Type': 'application/x-www-form-urlencoded'}

# XSTS / Xbox 返回的错误码 -> 中文说明（中国大陆账号常见坑）
XERR_HINT = {
    2148916233: '该微软账号是「儿童账号」，需由成年家庭成员在 family.microsoft.com 邀请你加入家庭组后才能使用 Xbox。',
    2148916238: '你的微软账号「地区」不支持 Xbox Live（中国大陆账号极常见）。\n解决：登录 account.microsoft.com 把地区改为支持的地区（如美国/香港），再用本账号重新登录；或换一个其他地区注册的微软账号。',
    2148916223: '该微软账号的 Xbox 服务已被封禁。',
    2148916226: '该微软账号暂时无法使用 Xbox（可能需要完成账号验证）。',
}


def _ms_req(method, url, **kw):
    """发请求并在出错时把微软的真实错误体（error_description / XErr）抛出来。"""
    try:
        r = requests.request(method, url, timeout=30, **kw)
    except requests.RequestException as e:
        raise Exception('网络请求失败: ' + str(e))
    if r.status_code >= 400:
        body = r.content.decode('utf-8', 'replace')
        try:
            j = r.json()
            if 'XErr' in j:
                code = j['XErr']
                body = 'Xbox 拒绝登录（XErr=%d）: %s' % (code, XERR_HINT.get(code, j.get('Message', '(未知 Xbox 错误)')))
            elif 'error' in j:
                desc = j.get('error_description') or j.get('error')
                body = (desc or body)
        except Exception:
            pass
        raise Exception('HTTP %d: %s' % (r.status_code, body[:600]))
    return r.json()


def offline_uuid(name):
    h = bytearray(hashlib.md5(('OfflinePlayer:' + name).encode('utf-8')).digest())
    h[6] = (h[6] & 0x0f) | 0x30
    h[8] = (h[8] & 0x3f) | 0x80
    return str(uuid.UUID(bytes=bytes(h)))


def create_offline(name):
    name = (name or 'Steve')[:16]
    return {'type': 'offline', 'name': name, 'uuid': offline_uuid(name),
            # 离线账号没有真实令牌，给一个非空的占位串：客户端要求 accessToken
            # 非空，历史上各版本官方启动器也是用 '0' 之类的占位值。
            'accessToken': '0', 'userType': 'mojang', 'userProperties': '[]',
            'xuid': '', 'createdAt': int(time.time() * 1000)}


def accounts_dir(data_root):
    return os.path.join(data_root, 'accounts')


def save_account(data_root, acc):
    d = accounts_dir(data_root)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, acc['uuid'] + '.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(acc, f, ensure_ascii=False, indent=2)


def list_accounts(data_root):
    d = accounts_dir(data_root)
    out = []
    if os.path.isdir(d):
        for fn in os.listdir(d):
            if fn.endswith('.json'):
                try:
                    with open(os.path.join(d, fn), 'r', encoding='utf-8') as f:
                        out.append(json.load(f))
                except Exception:
                    pass
    return out


def microsoft_device_code(client_id=CLIENT_ID):
    return _ms_req('POST', 'https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode',
                   data={'client_id': client_id, 'scope': SCOPE}, headers=UA)


def microsoft_poll(device_code, client_id=CLIENT_ID, interval=5, timeout=900):
    # 注意：微软 token 端点在「等待授权」时返回 HTTP 400 + error=authorization_pending，
    # 必须单独处理，不能用 _ms_req（那会直接抛异常中断轮询）。
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.post('https://login.microsoftonline.com/consumers/oauth2/v2.0/token',
                              data={'client_id': client_id,
                                    'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
                                    'device_code': device_code},
                              headers=UA, timeout=30)
        except requests.RequestException as e:
            raise Exception('网络请求失败: ' + str(e))
        if r.status_code == 200:
            return r.json()
        try:
            j = r.json()
            err = j.get('error')
        except Exception:
            j, err = {}, None
        if err == 'authorization_pending':
            time.sleep(interval)
            continue
        if err == 'slow_down':
            time.sleep(interval + 5)
            continue
        if err in ('expired_token', 'access_denied', 'authorization_declined'):
            raise Exception(err)
        body = r.content.decode('utf-8', 'replace')
        if 'error' in j:
            body = j.get('error_description') or j.get('error')
        raise Exception('HTTP %d: %s' % (r.status_code, body[:600]))
    raise Exception('timeout')


def xbl_token(ms_token):
    j = _ms_req('POST', 'https://user.auth.xboxlive.com/user/authenticate',
                json={'Properties': {'AuthMethod': 'RPS',
                                     'SiteName': 'user.auth.xboxlive.com',
                                     'RpsTicket': 'd=' + ms_token},
                      'RelyingParty': 'http://auth.xboxlive.com', 'TokenType': 'JWT'},
                headers={'Content-Type': 'application/json'})
    return j['Token'], j['DisplayClaims']['xui'][0]['uhs']


def xsts_token(xbl):
    j = _ms_req('POST', 'https://xsts.auth.xboxlive.com/xsts/authorize',
                json={'Properties': {'SandboxId': 'RETAIL', 'UserTokens': [xbl]},
                      'RelyingParty': 'rp://api.minecraftservices.com/', 'TokenType': 'JWT'},
                headers={'Content-Type': 'application/json'})
    return j['Token']


def mc_login(xbl, xsts, uhs):
    j = _ms_req('POST', 'https://api.minecraftservices.com/authentication/login_with_xbox',
                json={'identityToken': 'XBL3.0 x=%s;%s' % (uhs, xsts)},
                headers={'Content-Type': 'application/json'})
    return j['access_token']


def mc_profile(mc_token):
    return _ms_req('GET', 'https://api.minecraftservices.com/minecraft/profile',
                   headers={'Authorization': 'Bearer ' + mc_token})


def microsoft_login_flow(device_code_poll, client_id=CLIENT_ID):
    tok = microsoft_poll(device_code_poll['device_code'], client_id, device_code_poll.get('interval', 5))
    ms = tok['access_token']
    xbl, uhs = xbl_token(ms)
    xsts = xsts_token(xbl)
    mc = mc_login(xbl, xsts, uhs)
    prof = mc_profile(mc)
    return {'type': 'microsoft', 'name': prof['name'], 'uuid': prof['id'], 'accessToken': mc,
            'refreshToken': tok.get('refresh_token'), 'expiresIn': tok.get('expires_in'),
            'obtainedAt': int(time.time() * 1000), 'userType': 'mojang',
            'userProperties': json.dumps(prof.get('skins', [])), 'xuid': uhs,
            'skins': prof.get('skins', []), 'createdAt': int(time.time() * 1000)}


# ============================================================ 微软令牌刷新
def microsoft_refresh(acc, client_id=CLIENT_ID):
    """用 refresh_token 换新的访问令牌，并重新拉取角色资料。

    用于「刷新账号」按钮：正版登录后同步慢时点一下即可立即拿到最新
    accessToken 与皮肤数据，无需重新走一遍浏览器授权。
    """
    rt = acc.get('refreshToken')
    if not rt:
        raise Exception('该账号没有刷新令牌，无法刷新（请重新登录）')
    # 1) 微软 OAuth 刷新
    r = requests.post('https://login.microsoftonline.com/consumers/oauth2/v2.0/token',
                      data={'client_id': client_id,
                            'grant_type': 'refresh_token',
                            'refresh_token': rt,
                            'scope': SCOPE},
                      headers=UA, timeout=30)
    if r.status_code >= 400:
        body = r.content.decode('utf-8', 'replace')
        try:
            j = r.json()
            body = j.get('error_description') or j.get('error') or body
        except Exception:
            pass
        raise Exception('刷新微软令牌失败：%s' % body[:300])
    tok = r.json()
    ms = tok['access_token']
    # 2) 重新走 XBL / XSTS / MC 令牌交换
    xbl, uhs = xbl_token(ms)
    xsts = xsts_token(xbl)
    mc = mc_login(xbl, xsts, uhs)
    prof = mc_profile(mc)
    new = dict(acc)
    new.update({'name': prof['name'], 'uuid': prof['id'], 'accessToken': mc,
                'refreshToken': tok.get('refresh_token', rt),
                'expiresIn': tok.get('expires_in'),
                'obtainedAt': int(time.time() * 1000), 'xuid': uhs,
                'skins': prof.get('skins', []),
                'userProperties': json.dumps(prof.get('skins', []))})
    return new


# ============================================================ Yggdrasil 第三方登录服务器
# 兼容 authlib-injector 规范的登录服务器（如各类国服/私服皮肤站）。
# 接口： POST {server}/authserver/authenticate
#        POST {server}/authserver/refresh
#        POST {server}/authserver/invalidate
#        GET  {server}/minecraft/profile
YGG_HEADERS = {'Content-Type': 'application/json', 'User-Agent': 'ZMC-Launcher/1.0'}


def ygg_server_ok(server):
    """探测登录服务器是否可用（取其根路径的 metadata）"""
    from core.http import get_with_retry
    url = server.rstrip('/') + '/authserver/metadata'
    r = get_with_retry(url, tries=2, timeout=12)
    return True


def ygg_authenticate(server, user, password):
    """用户名密码登录第三方服务器，返回账号信息（含 accessToken/UUID）"""
    url = server.rstrip('/') + '/authserver/authenticate'
    payload = {
        'agent': {'name': 'Minecraft', 'version': 1},
        'username': user,
        'password': password,
        'clientToken': _client_token(),
        'requestUser': True,
    }
    r = _post_json(url, payload)
    j = r.json()
    if j.get('error'):
        raise Exception('登录失败：%s' % (j.get('errorMessage') or j.get('error')))
    # 取角色资料
    acc = _ygg_profile(server, j['accessToken'], j.get('selectedProfile', {}))
    acc['server'] = server
    acc['refreshToken'] = j.get('clientToken')
    acc['type'] = 'yggdrasil'
    return acc


def ygg_refresh(server, acc):
    """刷新第三方服务器账号的 accessToken"""
    payload = {
        'accessToken': acc.get('accessToken'),
        'clientToken': acc.get('refreshToken') or _client_token(),
        'selectedProfile': {'id': acc.get('uuid'), 'name': acc.get('name')},
        'requestUser': True,
    }
    url = server.rstrip('/') + '/authserver/refresh'
    r = _post_json(url, payload)
    j = r.json()
    if j.get('error'):
        raise Exception('刷新失败：%s' % (j.get('errorMessage') or j.get('error')))
    new = dict(acc)
    new.update(_ygg_profile(server, j['accessToken'], j.get('selectedProfile', {})))
    new['refreshToken'] = j.get('clientToken', acc.get('refreshToken'))
    new['server'] = server
    return new


def _ygg_profile(server, access_token, selected):
    """拉取角色资料（名字/UUID/皮肤）"""
    url = server.rstrip('/') + '/minecraft/profile'
    r = _get_json(url, {'Authorization': 'Bearer ' + access_token})
    if r.get('error'):
        raise Exception('获取角色失败：%s' % (r.get('errorMessage') or r.get('error')))
    props = []
    for p in r.get('properties', []) or []:
        if p.get('name') == 'textures':
            props.append({'name': 'textures', 'value': p.get('value', '')})
    return {'name': r.get('name') or selected.get('name'),
            'uuid': (r.get('id') or selected.get('id') or '').replace('-', ''),
            'accessToken': access_token,
            'userType': 'mojang',
            'userProperties': json.dumps(props),
            'skins': props,
            'xuid': '',
            'obtainedAt': int(time.time() * 1000)}


def _client_token():
    return uuid.uuid4().hex


def _post_json(url, payload, timeout=20):
    import requests as _rq
    r = _rq.post(url, json=payload, headers=YGG_HEADERS, timeout=timeout)
    if r.status_code >= 400:
        try:
            j = r.json()
            msg = j.get('errorMessage') or j.get('error')
        except Exception:
            msg = r.content.decode('utf-8', 'replace')[:200]
        raise Exception('HTTP %d：%s' % (r.status_code, msg))
    return r


def _get_json(url, headers, timeout=20):
    import requests as _rq
    r = _rq.get(url, headers=headers, timeout=timeout)
    if r.status_code >= 400:
        try:
            j = r.json()
            msg = j.get('errorMessage') or j.get('error')
        except Exception:
            msg = r.content.decode('utf-8', 'replace')[:200]
        raise Exception('HTTP %d：%s' % (r.status_code, msg))
    return r.json()
