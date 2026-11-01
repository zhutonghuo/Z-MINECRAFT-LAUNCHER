# -*- coding: utf-8 -*-
"""一次性生成启动器图标：Minecraft 风格草方块 + 品牌字母 Z。
输出 icon.png(512) 与 icon.ico(多尺寸)。
"""
import os
import math
from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SIZE = 512


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def round_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_base(size):
    """深色圆角背景 + 渐变 + 内描边"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(size * 0.06)
    box = (pad, pad, size - pad, size - pad)
    r = int(size * 0.18)
    # 渐变背景（竖直线性）
    bg_top = (54, 60, 78, 255)
    bg_bot = (22, 26, 36, 255)
    for y in range(int(box[1]), int(box[3])):
        t = (y - box[1]) / max(1, (box[3] - box[1]))
        col = lerp(bg_top, bg_bot, t)
        d.line([(box[0], y), (box[2], y)], fill=col)
    # 圆角遮罩：先画白圆角，再用它裁剪
    mask = Image.new('L', (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle(box, radius=r, fill=255)
    img.putalpha(mask)
    # 内描边
    d2 = ImageDraw.Draw(img)
    d2.rounded_rectangle([box[0] + 3, box[1] + 3, box[2] - 3, box[3] - 3],
                         radius=r - 3, outline=(120, 200, 255, 60), width=3)
    return img


def draw_cube(img, cx, cy, w):
    """等距草方块，中心(cx,cy)，宽度 w。返回正面用于放 Z 的区域。"""
    d = ImageDraw.Draw(img)
    hw = w / 2.0
    hh = w / 4.0  # 等距高度的一半
    top = (cx, cy - hh - hw * 0.5)  # 占位，下面用坐标计算

    # 顶点（等距菱形）
    T = (cx, cy - hh)                      # 上
    R = (cx + hw, cy)                      # 右
    B = (cx, cy + hh)                      # 下
    L = (cx - hw, cy)                      # 左
    T2 = (cx, cy - 2 * hh)                 # 顶面后点
    # 顶面（绿）
    top_face = [T, R, B, L]                # 这是中间菱形，不对；重算
    # 正确等距：顶面是 T2(后上), R(右), T(前中), L(左)
    top_face = [L, T2, R, T]
    # 左面（深棕）
    left_face = [L, T, B, (cx - hw, cy + 2 * hh)]  # 下左
    # 右面（中棕）
    right_face = [T, R, (cx + hw, cy + 2 * hh), B]

    green = (126, 200, 80, 255)
    green_d = (96, 168, 58, 255)
    left_brown = (94, 64, 38, 255)
    right_brown = (120, 82, 48, 255)
    edge = (40, 30, 20, 255)

    # 先画左右面，再画顶面
    d.polygon(left_face, fill=left_brown, outline=edge)
    d.polygon(right_face, fill=right_brown, outline=edge)
    d.polygon(top_face, fill=green, outline=edge)
    # 草与泥交界：顶面下沿加一条深绿描边
    d.line([L, T, R], fill=green_d, width=max(2, int(w * 0.012)))
    # 泥土斑点（右面）
    sp = int(w * 0.012)
    for _ in range(10):
        rx = R[0] - hw * (0.15 + 0.7 * ((_ * 37) % 100) / 100.0)
        ry = cy + hh * (0.2 + 0.6 * ((_ * 53) % 100) / 100.0)
        d.rectangle([rx, ry, rx + sp, ry + sp], fill=(80, 54, 32, 255))
    return (L, T, R, B, cx, cy)


def draw_z(img, cx, cy, w):
    """在方块正面叠加粗体 Z：先画深色描边再叠白色等宽笔画，干净利落"""
    d = ImageDraw.Draw(img)
    s = w * 0.50                 # Z 整体尺寸（留出边距）
    x0 = cx - s / 2
    x1 = cx + s / 2
    y0 = cy - s / 2
    y1 = cy + s / 2
    t = max(10, int(w * 0.16))   # 统一笔画粗细
    half = t / 2.0
    white = (245, 245, 250, 255)
    dark = (18, 14, 10, 235)
    out = max(3, int(w * 0.03))

    # 三个笔画中心线段：上横、斜、下横
    strokes = [
        ((x0, y0 + half), (x1, y0 + half)),          # 上横
        ((x1, y0 + half), (x0, y1 - half)),          # 斜
        ((x0, y1 - half), (x1, y1 - half)),          # 下横
    ]
    # 深色描边（更宽）
    for a, b in strokes:
        d.line([a, b], fill=dark, width=t + 2 * out, joint='curve')
    # 白色主体
    for a, b in strokes:
        d.line([a, b], fill=white, width=t, joint='curve')


def make_icon(size=SIZE):
    img = make_base(size)
    # 方块略小，居中偏上一点点给 Z 留空间
    cube_w = size * 0.46
    cx, cy = size * 0.5, size * 0.5
    draw_cube(img, cx, cy, cube_w)
    draw_z(img, cx, cy + size * 0.02, cube_w)
    # 轻微阴影增强立体感
    return img


if __name__ == '__main__':
    png = os.path.join(OUT_DIR, 'icon.png')
    ico = os.path.join(OUT_DIR, 'icon.ico')
    big = make_icon(SIZE)
    big.save(png)
    # 多尺寸 ico
    sizes = [16, 24, 32, 48, 64, 128, 256, 512]
    frames = []
    for s in sizes:
        f = big.resize((s, s), Image.LANCZOS)
        frames.append(f.convert('RGBA'))
    # PIL 保存 ico：传入尺寸列表
    frames[0].save(ico, sizes=[(s, s) for s in sizes], append_images=frames[1:],
                   format='ICO')
    print('已生成:', png, os.path.getsize(png), 'bytes')
    print('已生成:', ico, os.path.getsize(ico), 'bytes')
