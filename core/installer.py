import os

import requests

from core.config import rewrite_url
from core.download import Progress, download_all, failed_files, last_error
from core.extract import extract_natives
from core.http import friendly_error, get_bytes, get_json
from core.version import collect_assets, collect_downloads, merge_version, read_version_json


def ensure_version_json(data_root, source, version_id, version_url):
    """拉取版本 JSON。镜像节点失败时自动降级到官方源"""
    p = os.path.join(data_root, 'versions', version_id, version_id + '.json')
    if os.path.isfile(p):
        return True
    os.makedirs(os.path.dirname(p), exist_ok=True)
    try:
        content = get_bytes(rewrite_url(version_url, source), fallback=version_url,
                            tries=2, timeout=25)
    except Exception as e:
        raise Exception('无法获取版本信息（%s）：%s\n\n'
                        '请检查网络/代理设置，或在设置里把下载源换成「官方」后重试。'
                        % (version_id, friendly_error(e)))
    with open(p, 'wb') as f:
        f.write(content)
    return True


def is_installed(data_root, version_id):
    jar = os.path.join(data_root, 'versions', version_id, version_id + '.jar')
    return os.path.isfile(jar)


def _find_index_task(data_root, merged, tasks):
    ai = merged.get('assetIndex')
    if not ai:
        return None
    dest = os.path.join(data_root, 'assets', 'indexes', ai['id'] + '.json')
    for t in tasks:
        if t['dest'] == dest:
            return t
    return None


def install_vanilla(data_root, source, version_id, version_url,
                    progress_cb=None, item_cb=None, concurrency=16, segmented=None):
    prog = Progress(0, '准备下载')
    ensure_version_json(data_root, source, version_id, version_url)
    merged = merge_version(data_root, version_id)
    if not merged:
        raise Exception('无法解析版本信息：%s\n\n请删除该版本后重新安装，'
                        '或检查网络/代理设置。' % version_id)
    tasks = collect_downloads(data_root, source, merged, version_id)

    idx_task = _find_index_task(data_root, merged, tasks)
    if idx_task:
        prog.set_total(idx_task.get('size') or 0)
        download_all([idx_task], concurrency=1, progress_cb=progress_cb,
                     stage='下载资源索引', prog=prog, segmented=segmented)
        if not os.path.isfile(idx_task['dest']):
            raise Exception('资源索引下载失败：' + _reason())

    assets_tasks = collect_assets(data_root, source, merged)
    all_tasks = tasks + assets_tasks
    total = sum((t.get('size') or 0) for t in all_tasks)
    prog.set_total(total)
    ok = download_all(all_tasks, concurrency=concurrency, item_cb=item_cb,
                      progress_cb=progress_cb, stage='下载文件与资源', prog=prog,
                      segmented=segmented)

    if not ok:
        bad = failed_files()
        raise Exception(_failure_message(bad))

    prog.set_stage('解压原生库')
    prog.emit(progress_cb, True)
    extract_natives(data_root, version_id)

    prog.set_stage('安装完成')
    prog.emit(progress_cb, True)
    return True


def _reason():
    e = last_error()
    if e is None:
        return '未知原因'
    return friendly_error(e)


def _failure_message(bad):
    n = len(bad or [])
    head = '有 %d 个文件下载失败' % n
    detail = '、'.join(bad[:5]) + (' 等' if n > 5 else '')
    reason = _reason()
    msg = '%s（%s）' % (head, detail)
    if reason:
        msg += '\n原因：%s' % reason
    msg += '\n\n可尝试：\n· 在设置里把下载源换成「官方」\n· 或降低「下载并发数」后重试'
    return msg
