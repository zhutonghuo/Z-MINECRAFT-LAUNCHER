import os
import threading
import subprocess


def launch(cmd, cwd, log_cb=None, done_cb=None, log_path=None):
    env = dict(os.environ)
    # 彻底移除 JVM 工具选项注入变量（设空串仍会打印 "Picked up JAVA_TOOL_OPTIONS:"，
    # 部分 JDK 还会因空值解析异常退出），避免干扰游戏与安装器启动。
    for _k in ('JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS'):
        env.pop(_k, None)
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env)

    f = None
    if log_path:
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            f = open(log_path, 'wb')
        except Exception:
            f = None

    buf = b''

    def emit(raw):
        try:
            text = raw.decode('utf-8', 'replace').rstrip('\r')
        except Exception:
            text = str(raw)
        if log_cb:
            log_cb(text)

    def reader():
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            if f:
                try:
                    f.write(chunk)
                    f.flush()
                except Exception:
                    pass
            nonlocal buf
            buf += chunk
            while True:
                nl = buf.find(b'\n')
                if nl < 0:
                    break
                emit(buf[:nl])
                buf = buf[nl + 1:]
        if buf:
            emit(buf)
        if f:
            try:
                f.close()
            except Exception:
                pass

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    rc = proc.wait()
    t.join(timeout=2.0)
    if done_cb:
        done_cb(rc)
    return rc
