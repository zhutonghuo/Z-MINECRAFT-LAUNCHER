# -*- coding: utf-8 -*-
"""最小但保真的 NBT 解析 / 序列化工具。

用途：读取与修改 Minecraft 世界的 level.dat（世界名称、存档信息）。
要求：解析后再写回必须保持每个标签的原始类型（Byte/Short/Int/Long/...），
否则游戏读取存档可能报错。因此这里用「带类型的节点」表示整棵树，
而非直接用 Python 原生 int/float（那样会丢失类型信息）。

仅实现 Minecraft 实际用到的标签类型，足够覆盖 level.dat。
"""
import gzip
import io
import os
import shutil
import struct

END = 0
BYTE = 1
SHORT = 2
INT = 3
LONG = 4
FLOAT = 5
DOUBLE = 6
BYTE_ARR = 7
STRING = 8
LIST = 9
COMPOUND = 10
INT_ARR = 11
LONG_ARR = 12


class NbtError(Exception):
    pass


class _Tag:
    tid = END

    def to_py(self):
        """递归转换为原生 Python 对象（仅用于显示/调试，不用于回写）。"""
        return None


class TByte(_Tag):
    tid = BYTE

    def __init__(self, v):
        self.v = int(v)

    def to_py(self):
        return self.v


class TShort(_Tag):
    tid = SHORT

    def __init__(self, v):
        self.v = int(v)

    def to_py(self):
        return self.v


class TInt(_Tag):
    tid = INT

    def __init__(self, v):
        self.v = int(v)

    def to_py(self):
        return self.v


class TLong(_Tag):
    tid = LONG

    def __init__(self, v):
        self.v = int(v)

    def to_py(self):
        return self.v


class TFloat(_Tag):
    tid = FLOAT

    def __init__(self, v):
        self.v = float(v)

    def to_py(self):
        return self.v


class TDouble(_Tag):
    tid = DOUBLE

    def __init__(self, v):
        self.v = float(v)

    def to_py(self):
        return self.v


class TByteArray(_Tag):
    tid = BYTE_ARR

    def __init__(self, v):
        self.v = bytes(v)

    def to_py(self):
        return self.v


class TString(_Tag):
    tid = STRING

    def __init__(self, v):
        self.v = str(v)

    def to_py(self):
        return self.v


class TList(_Tag):
    tid = LIST

    def __init__(self, elem_tid, items):
        self.elem_tid = int(elem_tid)
        self.items = list(items)

    def to_py(self):
        return [i.to_py() for i in self.items]


class TCompound(_Tag):
    tid = COMPOUND

    def __init__(self, d=None):
        self.d = d or {}

    def to_py(self):
        return {k: v.to_py() for k, v in self.d.items()}


class TIntArray(_Tag):
    tid = INT_ARR

    def __init__(self, v):
        self.v = [int(x) for x in v]

    def to_py(self):
        return self.v


class TLongArray(_Tag):
    tid = LONG_ARR

    def __init__(self, v):
        self.v = [int(x) for x in v]

    def to_py(self):
        return self.v


def _u1(f):
    b = f.read(1)
    if len(b) < 1:
        raise NbtError('NBT 数据意外截断')
    return b[0]


def _u2(f):
    b = f.read(2)
    if len(b) < 2:
        raise NbtError('NBT 数据意外截断')
    return struct.unpack('>H', b)[0]


def _u4(f):
    b = f.read(4)
    if len(b) < 4:
        raise NbtError('NBT 数据意外截断')
    return struct.unpack('>I', b)[0]


def _u8(f):
    b = f.read(8)
    if len(b) < 8:
        raise NbtError('NBT 数据意外截断')
    return struct.unpack('>Q', b)[0]


def _read_payload(tid, f):
    if tid == BYTE:
        return TByte(_u1(f))
    if tid == SHORT:
        return TShort(struct.unpack('>h', f.read(2))[0])
    if tid == INT:
        return TInt(struct.unpack('>i', f.read(4))[0])
    if tid == LONG:
        return TLong(struct.unpack('>q', f.read(8))[0])
    if tid == FLOAT:
        return TFloat(struct.unpack('>f', f.read(4))[0])
    if tid == DOUBLE:
        return TDouble(struct.unpack('>d', f.read(8))[0])
    if tid == BYTE_ARR:
        n = _u4(f)
        return TByteArray(f.read(n))
    if tid == STRING:
        n = _u2(f)
        return TString(f.read(n).decode('utf-8', 'replace'))
    if tid == LIST:
        etid = _u1(f)
        n = _u4(f)
        items = [_read_payload(etid, f) for _ in range(n)]
        return TList(etid, items)
    if tid == COMPOUND:
        d = {}
        while True:
            ctid = _u1(f)
            if ctid == END:
                break
            name = _read_payload(STRING, f).v
            d[name] = _read_payload(ctid, f)
        return TCompound(d)
    if tid == INT_ARR:
        n = _u4(f)
        return TIntArray([struct.unpack('>i', f.read(4))[0] for _ in range(n)])
    if tid == LONG_ARR:
        n = _u4(f)
        return TLongArray([struct.unpack('>q', f.read(8))[0] for _ in range(n)])
    raise NbtError('不支持的 NBT 标签类型：%d' % tid)


def parse_nbt(data):
    """解析 NBT 字节流，返回根 TCompound。"""
    f = io.BytesIO(data)
    root_tid = _u1(f)
    if root_tid != COMPOUND:
        raise NbtError('根标签不是 COMPOUND（实际 %d）' % root_tid)
    _read_payload(STRING, f)  # 根节点名称（通常为空）
    return _read_payload(COMPOUND, f)


def _write_payload(tag, f):
    tid = tag.tid
    if tid == BYTE:
        f.write(struct.pack('>b', tag.v & 0xFF if tag.v >= 0 else tag.v))
    elif tid == SHORT:
        f.write(struct.pack('>h', tag.v))
    elif tid == INT:
        f.write(struct.pack('>i', tag.v))
    elif tid == LONG:
        f.write(struct.pack('>q', tag.v))
    elif tid == FLOAT:
        f.write(struct.pack('>f', tag.v))
    elif tid == DOUBLE:
        f.write(struct.pack('>d', tag.v))
    elif tid == BYTE_ARR:
        f.write(struct.pack('>i', len(tag.v)))
        f.write(tag.v)
    elif tid == STRING:
        b = tag.v.encode('utf-8')
        f.write(struct.pack('>h', len(b)))
        f.write(b)
    elif tid == LIST:
        f.write(bytes([tag.elem_tid]))
        f.write(struct.pack('>i', len(tag.items)))
        for it in tag.items:
            _write_payload(it, f)
    elif tid == COMPOUND:
        for name, sub in tag.d.items():
            f.write(bytes([sub.tid]))
            bn = name.encode('utf-8')
            f.write(struct.pack('>h', len(bn)))
            f.write(bn)
            _write_payload(sub, f)
        f.write(bytes([END]))
    elif tid == INT_ARR:
        f.write(struct.pack('>i', len(tag.v)))
        for x in tag.v:
            f.write(struct.pack('>i', x))
    elif tid == LONG_ARR:
        f.write(struct.pack('>i', len(tag.v)))
        for x in tag.v:
            f.write(struct.pack('>q', x))
    else:
        raise NbtError('无法序列化标签类型：%d' % tid)


def serialize_nbt(root):
    """把根 TCompound 序列化为 NBT 字节流（含根类型与空名）。"""
    f = io.BytesIO()
    f.write(bytes([COMPOUND]))
    f.write(struct.pack('>h', 0))  # 根名称长度 0
    _write_payload(root, f)
    return f.getvalue()


# ---------------------------------------------------------------- level.dat
def read_level_dat(path):
    """读取 level.dat，返回根 TCompound；文件不存在或损坏返回 None。"""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'rb') as fp:
            raw = fp.read()
        return parse_nbt(gzip.decompress(raw))
    except Exception:
        return None


def get_level_name(path):
    """从 level.dat 读取世界显示名称（Data.LevelName）。"""
    root = read_level_dat(path)
    if not isinstance(root, TCompound):
        return None
    data = root.d.get('Data')
    if not isinstance(data, TCompound):
        return None
    nm = data.d.get('LevelName')
    if isinstance(nm, TString):
        return nm.v
    return None


def set_level_name(path, new_name):
    """修改 level.dat 里的 Data.LevelName，写回前自动备份，写后校验，失败回滚。

    返回 True 表示成功；失败时恢复原文件并抛出异常。
    """
    root = read_level_dat(path)
    if not isinstance(root, TCompound):
        raise NbtError('无法解析 level.dat：文件可能已损坏')
    data = root.d.get('Data')
    if not isinstance(data, TCompound):
        data = TCompound({})
        root.d['Data'] = data
    data.d['LevelName'] = TString(new_name)
    out = gzip.compress(serialize_nbt(root))
    backup = path + '.bak'
    made_backup = False
    try:
        shutil.copy2(path, backup)
        made_backup = True
    except Exception:
        made_backup = False
    try:
        with open(path, 'wb') as fp:
            fp.write(out)
        # 写后校验：能重新解析且名称一致
        chk = get_level_name(path)
        if chk != new_name:
            raise NbtError('写入校验未通过')
    except Exception as e:
        if made_backup and os.path.isfile(backup):
            shutil.copy2(backup, path)
        raise NbtError('世界名称写入失败，已恢复原文件：%s' % e)
    finally:
        if made_backup and os.path.isfile(backup):
            try:
                os.remove(backup)
            except OSError:
                pass
    return True
