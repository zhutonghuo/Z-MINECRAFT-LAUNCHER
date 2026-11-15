import hashlib
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from core.http import (circuit_open, is_transient, make_session,
                       report_failure, report_success)

CHUNK = 262144
SEG_MIN = 4 * 1024 * 1024
SPEED_WINDOW = 3.0
EMIT_INTERVAL = 0.12

_LOCAL = threading.local()
_SEM_LOCK = threading.Lock()
# 代理版本号：代理设置变化时递增，强制各线程重建 Session
_PROXY_VER = 0
_CONN_SEM = threading.Semaphore(16)
_CONN_LIMIT = 16
_SEGMENTED = True
_LAST_ERROR = None
_FAILED_FILES = []


def last_error():
    return _LAST_ERROR


def failed_files():
    return list(_FAILED_FILES)


def set_connection_limit(n):
    global _CONN_SEM, _CONN_LIMIT
    with _SEM_LOCK:
        n = max(1, int(n))
        _CONN_SEM = threading.Semaphore(n)
        _CONN_LIMIT = n


def set_segmented(enabled):
    """开关大文件分段并行下载"""
    global _SEGMENTED
    with _SEM_LOCK:
        _SEGMENTED = bool(enabled)


def sync_proxy_version(ver):
    """代理变更时同步版本号，使各线程下次取 Session 时重建"""
    global _PROXY_VER
    _PROXY_VER = ver


def get_session():
    s = getattr(_LOCAL, 'session', None)
    if s is None or getattr(_LOCAL, 'proxy_ver', -1) != _PROXY_VER:
        s = make_session(pool=32, retries=3, backoff=0.4)
        s.headers.update({'Accept-Encoding': 'identity'})
        _LOCAL.session = s
        _LOCAL.proxy_ver = _PROXY_VER
    return s


def file_sha1(path, block=1048576):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(block), b''):
            h.update(b)
    return h.hexdigest()


class Progress:
    def __init__(self, total_bytes=0, stage='准备'):
        self.lock = threading.Lock()
        self.total = total_bytes
        self.done = 0
        self.stage = stage
        self.current = ''
        self.files_done = 0
        self.files_total = 0
        self._samples = deque(maxlen=256)
        self._last = 0.0

    def set_stage(self, stage):
        with self.lock:
            self.stage = stage

    def set_total(self, total):
        with self.lock:
            self.total = total

    def add_bytes(self, n, name=''):
        with self.lock:
            self.done += n
            if name:
                self.current = name

    def add_file(self):
        with self.lock:
            self.files_done += 1

    def emit(self, cb, force=False):
        if cb is None:
            return
        with self.lock:
            now = time.time()
            if not force and now - self._last < EMIT_INTERVAL:
                return
            self._last = now
            self._samples.append((now, self.done))
            while len(self._samples) > 2 and self._samples[0][0] < now - SPEED_WINDOW:
                self._samples.popleft()
            if len(self._samples) >= 2:
                t0, d0 = self._samples[0]
                dt = now - t0
                speed = (self.done - d0) / dt if dt > 0.3 else 0.0
            else:
                speed = 0.0
            info = {
                'stage': self.stage,
                'done': self.done,
                'total': self.total,
                'speed': max(0.0, speed),
                'name': self.current,
                'files_done': self.files_done,
                'files_total': self.files_total,
            }
        cb(info)


def _stream(url, dest_path, on_bytes, start=None, end=None, resume=None, timeout=45):
    """流式下载。

    timeout 拆成 (连接超时, 读取超时)：镜像节点挂起时能较快放弃并切换到官方源，
    读取超时放宽以适应大文件慢速传输。
    """
    sess = get_session()
    headers = {}
    if start is not None:
        headers['Range'] = 'bytes=%d-%d' % (start, end)
    elif resume:
        headers['Range'] = 'bytes=%d-' % resume
    conn_timeout = min(15, timeout)
    with _CONN_SEM:
        with sess.get(url, stream=True, timeout=(conn_timeout, timeout),
                      headers=headers) as r:
            if start is not None:
                if r.status_code != 206:
                    raise Exception('服务器不支持分段下载')
                # 分段写入的是独立临时文件，内容从 0 开始，无需 seek
                mode, offset = 'wb', None
            elif resume and r.status_code == 206:
                mode, offset = 'ab', None
            else:
                mode, offset = 'wb', None
            r.raise_for_status()
            with open(dest_path, mode) as f:
                if offset is not None:
                    f.seek(offset)
                for data in r.iter_content(CHUNK):
                    if not data:
                        continue
                    f.write(data)
                    if on_bytes:
                        on_bytes(len(data))
            return r.status_code


def _seg_count(size):
    """大文件分段数：受全局连接上限约束，单文件最多 8 段"""
    if size < SEG_MIN:
        return 1
    limit = max(1, min(8, _CONN_LIMIT))
    return max(1, min(limit, size // SEG_MIN))


def _segmented(url, dest, size, sha1, segments, on_delta):
    tmp = dest + '.part'
    parts = [tmp + '.seg%d' % i for i in range(segments)]
    errors = []
    counted = [0]

    def track(n):
        counted[0] += n
        if on_delta:
            on_delta(n)

    def worker(idx):
        start = idx * (size // segments)
        end = start + (size // segments) - 1
        if idx == segments - 1:
            end = size - 1
        try:
            _stream(url, parts[idx], track, start=start, end=end)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(segments):
        t = threading.Thread(target=worker, args=(i,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    if errors:
        if on_delta and counted[0]:
            on_delta(-counted[0])   # 回滚本轮计数，避免重试时进度虚高
        raise errors[0]
    try:
        with open(tmp, 'wb') as out:
            for p in parts:
                with open(p, 'rb') as src:
                    while True:
                        buf = src.read(1024 * 1024)
                        if not buf:
                            break
                        out.write(buf)
    finally:
        for p in parts:
            try:
                os.remove(p)
            except OSError:
                pass
    if sha1 and file_sha1(tmp) != sha1:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if on_delta and counted[0]:
            on_delta(-counted[0])
        return False
    return True


def download_file(url, dest, sha1=None, size=None, chunk=CHUNK, on_delta=None, name=None,
                  fallback=None):
    """下载单个文件。

    fallback: 官方源地址。镜像节点连不上时自动改用官方源重试
    （BMCLAPI 会 302 到多个第三方节点，那些节点常在高并发下断连）。
    返回 True 成功；False 失败（不抛异常，避免单个文件拖垮整个安装）。
    """
    if sha1 and os.path.isfile(dest):
        try:
            if file_sha1(dest) == sha1:
                if on_delta:
                    on_delta(size or 0)
                return True
        except OSError:
            pass
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'

    # 先试镜像，失败再试官方源
    attempts = [url]
    if fallback and fallback != url:
        attempts.append(fallback)

    last_err = None
    for url_idx, cur_url in enumerate(attempts):
        is_last = (url_idx == len(attempts) - 1)
        # 熔断打开时跳过镜像，直接用官方源
        if url_idx == 0 and len(attempts) > 1 and circuit_open():
            continue
        # 镜像只重试 2 次（快速降级），官方源给 3 次
        tries = 3 if is_last else 2
        for attempt in range(tries):
            have = 0
            if os.path.exists(tmp):
                try:
                    have = os.path.getsize(tmp)
                except OSError:
                    have = 0
            if have and sha1 and file_sha1(tmp) == sha1:
                os.replace(tmp, dest)
                return True
            if not have and size and size >= SEG_MIN and _SEGMENTED:
                n = _seg_count(size)
                if n > 1:
                    try:
                        if _segmented(cur_url, dest, size, sha1, n, on_delta):
                            os.replace(dest + '.part', dest)
                            if url_idx == 0:
                                report_success()
                            return True
                        last_err = Exception('SHA1 校验不通过')
                        break
                    except Exception as e:
                        last_err = e
                        if url_idx == 0:
                            report_failure()
                        for p in [dest + '.part'] + [dest + '.part.seg%d' % i
                                                    for i in range(n)]:
                            try:
                                os.remove(p)
                            except OSError:
                                pass
                        if is_transient(e):
                            time.sleep(0.3 * (2 ** attempt))
                            continue
                        break   # 非瞬时错误，换下一个源
            try:
                before = have
                if before and on_delta:
                    on_delta(before)   # 已存在的部分计入总进度
                status = _stream(cur_url, tmp,
                                 lambda n: on_delta(n) if on_delta else None,
                                 resume=have or None)
                if before and status != 206 and on_delta:
                    on_delta(-before)  # 服务器不支持续传、从头重下，撤销已计入的部分
                if sha1 and file_sha1(tmp) != sha1:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    last_err = Exception('SHA1 校验不通过')
                    break
                os.replace(tmp, dest)
                if url_idx == 0:
                    report_success()
                return True
            except Exception as e:
                last_err = e
                if url_idx == 0:
                    report_failure()
                if is_transient(e):
                    time.sleep(0.3 * (2 ** attempt))
                    continue
                break   # 非瞬时错误，直接换源
        # 该源彻底失败，尝试下一个源（官方）
    if last_err is not None:
        _LAST_ERROR = last_err
    return False


def download_all(tasks, concurrency=16, item_cb=None, progress_cb=None, stage='下载',
                 prog=None, segmented=None):
    set_connection_limit(concurrency)
    if segmented is not None:
        set_segmented(segmented)
    if prog is None:
        prog = Progress(sum((t.get('size') or 0) for t in tasks), stage)
    else:
        prog.set_stage(stage)
    total_files = len(tasks)
    prog.files_total = total_files
    if not tasks:
        prog.emit(progress_cb, True)
        return True
    ok = True
    done_files = 0
    failed = []

    def make_cb(name):
        def cb(n):
            prog.add_bytes(n, name)
            prog.emit(progress_cb)
        return cb

    base_stage = stage

    def check_circuit():
        """熔断打开时更新阶段文案，告知用户已切换官方源"""
        if circuit_open():
            prog.set_stage(base_stage + '（镜像不稳定，已切换官方源）')
        elif prog.stage == base_stage + '（镜像不稳定，已切换官方源）':
            prog.set_stage(base_stage)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {}
        for t in tasks:
            name = os.path.basename(t['dest'])
            fu = ex.submit(download_file, t['url'], t['dest'], t.get('sha1'), t.get('size'),
                           CHUNK, make_cb(name), name, t.get('fallback'))
            futures[fu] = t
        prog.emit(progress_cb, True)
        for fu in as_completed(list(futures)):
            t = futures[fu]
            try:
                res = fu.result()
            except Exception as e:
                res = False
                _LAST_ERROR = e
            done_files += 1
            prog.add_file()
            if not res:
                ok = False
                failed.append(os.path.basename(t['dest']))
            if item_cb:
                item_cb(done_files, total_files, t, res)
            prog.emit(progress_cb)
    prog.emit(progress_cb, True)
    if failed and not ok:
        _FAILED_FILES = failed
    return ok
