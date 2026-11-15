import json
import os

import requests

from core.http import get_with_retry

API = 'https://api.modrinth.com/v2'
UA = {'User-Agent': 'ZMC-Launcher/1.0 (PyQt5 desktop launcher)'}

PROJECT_TYPES = [
    ('mod', '模组'),
    ('resourcepack', '资源包'),
    ('shader', '光影'),
    ('modpack', '整合包'),
]

FOLDER_BY_TYPE = {
    'mod': 'mods',
    'resourcepack': 'resourcepacks',
    'shader': 'shaderpacks',
    'modpack': 'modpacks',
}


def api_get(path, params=None):
    r = get_with_retry(API + path, tries=3, timeout=30, params=params)
    if r.status_code >= 400:
        body = r.content.decode('utf-8', 'replace')[:300]
        raise Exception('Modrinth API 错误 %d：%s' % (r.status_code, body))
    return r.json()


def search_projects(query, project_type='mod', mc_version='', offset=0, limit=24):
    facets = [['project_type:' + project_type]]
    if mc_version:
        facets.append(['versions:' + mc_version])
    data = api_get('/search', params={
        'query': query,
        'facets': json.dumps(facets),
        'index': 'relevance',
        'limit': limit,
        'offset': offset,
    })
    hits = []
    for h in data.get('hits', []):
        hits.append({
            'id': h.get('project_id'),
            'slug': h.get('slug'),
            'title': h.get('title'),
            'description': h.get('description'),
            'icon_url': h.get('icon_url'),
            'downloads': h.get('downloads', 0),
            'follows': h.get('follows', 0),
            'author': h.get('author'),
            'project_type': h.get('project_type'),
            'categories': h.get('display_categories') or [],
            'date_modified': h.get('date_modified'),
        })
    return {'hits': hits, 'total': data.get('total_hits') or data.get('total') or 0,
            'offset': data.get('offset', 0)}


def get_project(project_id):
    return api_get('/project/' + project_id)


def get_versions(project_id):
    return api_get('/project/%s/version' % project_id)


def pick_version_file(versions, mc_version):
    compatible = [v for v in versions
                  if (not mc_version or mc_version in (v.get('game_versions') or []))
                  and v.get('version_type') in ('release', 'beta', 'alpha')]
    lst = compatible or versions
    for v in lst:
        for f in (v.get('files') or []):
            env = f.get('env') or {}
            if f.get('primary') or env.get('client') != 'unsupported':
                return v, f
    if lst and lst[0].get('files'):
        return lst[0], lst[0]['files'][0]
    return None, None


def resolve_download(project_id, project_type='mod', mc_version=''):
    """解析出要下载的文件信息（不下载）"""
    versions = get_versions(project_id)
    v, f = pick_version_file(versions, mc_version)
    if not f:
        raise Exception('未找到兼容该游戏版本的文件')
    folder = FOLDER_BY_TYPE.get(project_type, 'mods')
    return {
        'filename': f.get('filename'),
        'url': f.get('url'),
        'sha1': (f.get('hashes') or {}).get('sha1'),
        'size': f.get('size') or 0,
        'version': v.get('name') or v.get('version_number') or '',
        'folder': folder,
    }


def target_path(game_dir, project_type, filename):
    folder = FOLDER_BY_TYPE.get(project_type, 'mods')
    dest_dir = os.path.join(game_dir, folder)
    os.makedirs(dest_dir, exist_ok=True)
    return os.path.join(dest_dir, filename)


def fetch_icon(url, dest, size=64):
    """下载项目图标（纯装饰，失败不影响）"""
    try:
        r = get_with_retry(url, tries=2, timeout=15)
        if r.status_code >= 400:
            return False
        with open(dest, 'wb') as f:
            f.write(r.content)
        return True
    except Exception:
        return False
