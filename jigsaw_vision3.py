# -*- coding: utf-8 -*-
"""画布巡回拼图 · 视觉 v3(布局自适应)
不依赖固定像素坐标。输入 RGB ndarray(一条龙截图, 已归一化 1920x1080)。
屏幕识别全部基于画面特征: 绿勾行聚类(关卡页) / 亮色棋盘连通域(拼图盘) / 黄色页签(页签态)。
"""
import cv2
import numpy as np

NS = (3, 4, 5, 6)
INSET = 0.08

# ---------- 颜色掩码(RGB) ----------
def green_mask(img):
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    return (g > 150) & (r < 120) & (b < 120) & (g - r > 60) & (g - b > 60)


def orange_mask(img):
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    return (r >= 185) & (g >= 120) & (g <= 215) & (b <= 125)


def blue_mask(img):
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    return (r >= 25) & (r <= 115) & (g >= 65) & (g <= 150) & (b >= 145) & (b <= 235)


def tab_yellow_mask(img):
    r, g, b = img[:, :, 0].astype(int), img[:, :, 1].astype(int), img[:, :, 2].astype(int)
    return (r > 200) & (g > 170) & (b < 110)


# ---------- 通用: 色块按行聚类 ----------
def cluster_rows(mask, min_pix=60, x_offset=0):
    """掩码像素按 y 聚类成行(行间距 < 60px 合并), 返回按 y 升序的
    [{y0, y1, y, x0, x1, count}]"""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return []
    order = np.argsort(ys)
    ys, xs = ys[order], xs[order]
    groups = []
    cur = [0]
    for idx in range(1, len(ys)):
        if ys[idx] - ys[cur[-1]] <= 40:
            cur.append(idx)
        else:
            groups.append(cur)
            cur = [idx]
    groups.append(cur)
    rows = []
    for g in groups:
        if len(g) < min_pix:
            continue
        gy, gx = ys[g], xs[g]
        rows.append({'y0': int(gy.min()), 'y1': int(gy.max()), 'y': int((gy.min() + gy.max()) // 2),
                     'x0': int(gx.min() + x_offset), 'x1': int(gx.max() + x_offset),
                     'count': int(len(g))})
    merged = []
    for r in sorted(rows, key=lambda t: t['y0']):
        if merged and r['y0'] - merged[-1]['y1'] < 60:
            m = merged[-1]
            m['y1'] = max(m['y1'], r['y1'])
            m['x0'] = min(m['x0'], r['x0'])
            m['x1'] = max(m['x1'], r['x1'])
            m['count'] += r['count']
            m['y'] = (m['y0'] + m['y1']) // 2
        else:
            merged.append(dict(r))
    return merged


# ---------- 关卡选择页 ----------
def level_rows(img):
    """关卡行动态检测: 右半区绿勾聚类。
    返回 [{y, x0, x1, done, green}] 按钮点击位 = (x0-300, y)。"""
    h, w = img.shape[:2]
    mask = green_mask(img)[:, w // 2:]
    rows = cluster_rows(mask, min_pix=60, x_offset=w // 2)
    out = []
    for r in rows:
        r = dict(r)
        r['done'] = r['count'] >= 550   # 三勾齐 ≈ 750px, 一勾 ≈ 250px
        out.append(r)
    return out


def is_level_page(img):
    rows = level_rows(img)
    return len(rows) >= 3


def first_unfinished_click(img):
    """返回第一个未完成关卡的点击位置 (x, y); 全完成返回 None"""
    rows = level_rows(img)
    for r in rows:
        if not r['done']:
            return (max(200, r['x0'] - 300), r['y'])
    return None


# ---------- 拼图盘 ----------
def find_board(img):
    """拼图盘检测: 右半区最大亮色连通域外接框 (x0,y0,x1,y1); 失败 None"""
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    right = gray[:, int(w * 0.45):]
    bright = (right > 70).astype(np.uint8) * 255
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(bright)
    best = None
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < 40000 or bw < w * 0.28 or bh < h * 0.45:
            continue
        if best is None or area > best[4]:
            best = (x + int(w * 0.45), y, bw, bh, area)
    if best is None:
        return None
    x, y, bw, bh, _ = best
    return (x, y, x + bw, y + bh)


def view_state_v3(img, board=None):
    """'puzzle'=拼图视图 / 'image'=原图视图 / None(其余)。
    依据: 棋盘左下区(或原图区)有无橙/蓝按钮色块。"""
    h, w = img.shape[:2]
    b = board if board else find_board(img)
    if b is None:
        return None
    x0, y0, x1, y1 = b
    zone = img[max(0, y1 - 220):y1, max(0, x0 - 200):x0]
    o = float(orange_mask(zone).mean())
    bl = float(blue_mask(zone).mean())
    if o > 0.10:
        return 'puzzle'
    if bl > 0.10:
        return 'image'
    return None


def active_tab_index_v3(img, board):
    """激活页签: 黄色块中心落在棋盘宽的三等分槽位。未识别 None"""
    h, w = img.shape[:2]
    ymask = tab_yellow_mask(img)[: int(h * 0.2), :]
    ys, xs = np.nonzero(ymask)
    if len(xs) < 20:
        return None
    cx = (min(xs) + max(xs)) / 2
    x0, _, x1, _ = board
    pitch = (x1 - x0) / 3
    idx = int((cx - x0) / pitch)
    if 0 <= idx < 3:
        return idx
    return None


def tab_completed(img, board, idx):
    """页签 idx 是否有绿勾: 勾在页签槽位右上角"""
    h, w = img.shape[:2]
    x0, _, x1, _ = board
    pitch = (x1 - x0) / 3
    zx0 = int(x0 + (idx + 1) * pitch - 75)
    zone = img[int(60):int(130), zx0:zx0 + 70]
    if zone.size == 0:
        return None
    return float(green_mask(zone).mean()) > 0.02


# ---------- 棋盘内格子 ----------
def cut_cells(img, box, n):
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / n, (y1 - y0) / n
    out = []
    for r in range(n):
        for c in range(n):
            ax0 = int(x0 + c * cw + cw * INSET); ay0 = int(y0 + r * ch + ch * INSET)
            ax1 = int(x0 + (c + 1) * cw - cw * INSET); ay1 = int(y0 + (r + 1) * ch - ch * INSET)
            out.append(img[ay0:ay1, ax0:ax1])
    return out


def cell_center(k, n, box):
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / n, (y1 - y0) / n
    return (x0 + (k % n + 0.5) * cw, y0 + (k // n + 0.5) * ch)


def _ncc_sim(a, b):
    def ch(img):
        img = cv2.resize(img, (64, 64)).astype(np.float32)
        img = (img - img.mean()) / (img.std() + 1e-6)
        return img
    vals = []
    for i in range(3):
        pa, pb = ch(a[:, :, i]), ch(b[:, :, i])
        vals.append(float((pa * pb).mean()))
    return sum(vals) / 3


def match_by_template(board, ref, n, box):
    cwb, chb = (box[2] - box[0]) / n, (box[3] - box[1]) / n
    ix, iy = int(cwb * INSET), int(chb * INSET)
    sx0, sy0 = max(0, int(box[0] - 80)), max(0, int(box[1] - 80))
    sx1, sy1 = min(board.shape[1], int(box[2] + 80)), min(board.shape[0], int(box[3] + 80))
    rg = cv2.cvtColor(ref[sy0:sy1, sx0:sx1], cv2.COLOR_BGR2GRAY)
    hits = []
    for c in cut_cells(board, box, n):
        t = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
        m = cv2.matchTemplate(rg, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(m)
        hits.append((loc[0] + sx0 - ix, loc[1] + sy0 - iy, score))
    xs = sorted(h[0] for h in hits)
    ys = sorted(h[1] for h in hits)
    px, py = (xs[-1] - xs[0]) / (n - 1), (ys[-1] - ys[0]) / (n - 1)
    if not (0.6 * cwb < px < 1.6 * cwb) or not (0.6 * chb < py < 1.6 * chb):
        return None, 0.0
    perm = []
    for hx, hy, sc in hits:
        col = max(0, min(n - 1, round((hx - xs[0]) / px)))
        row = max(0, min(n - 1, round((hy - ys[0]) / py)))
        perm.append(row * n + col)
    if sorted(perm) != list(range(n * n)):
        return None, 0.0
    return perm, float(np.mean([h[2] for h in hits]))


def match_by_cells(board, ref, n, box):
    bc = cut_cells(board, box, n)
    rc = cut_cells(ref, box, n)
    cnt = n * n
    S = np.zeros((cnt, cnt))
    for i, a in enumerate(bc):
        for j, b in enumerate(rc):
            S[i, j] = _ncc_sim(a, b)
    taken = set()
    perm = [-1] * cnt
    for i in np.argsort(-S.max(axis=1)):
        for j in np.argsort(-S[int(i)]):
            if int(j) not in taken:
                perm[int(i)] = int(j)
                taken.add(int(j))
                break
    return perm, float(np.mean(S[np.arange(cnt), perm]))


def detect_grid(board, ref, box):
    best = None
    for n in NS:
        perm, score = match_by_template(board, ref, n, box)
        if perm is not None and (best is None or score > best[2]):
            best = (n, perm, score, '模板匹配')
    if best is not None:
        return best
    best = None
    for n in NS:
        perm, score = match_by_cells(board, ref, n, box)
        if best is None or score > best[2]:
            best = (n, perm, score, '逐格比对')
    return best


def solve_perm(perm):
    p = perm[:]
    swaps = []
    for i in range(len(p)):
        while p[i] != i:
            j = p.index(i)
            p[i], p[j] = p[j], p[i]
            swaps.append((j, i))
            if len(swaps) > 60:
                raise RuntimeError('swap runaway')
    return swaps


def cells_diff(pre, post, a, b, n, box):
    pa, pb = cut_cells(pre, box, n), cut_cells(post, box, n)
    d = 0.0
    for k in (a, b):
        h = min(pa[k].shape[0], pb[k].shape[0]); w = min(pa[k].shape[1], pb[k].shape[1])
        d += float(np.abs(pa[k][:h, :w].astype(int) - pb[k][:h, :w].astype(int)).mean())
    return d / 2
