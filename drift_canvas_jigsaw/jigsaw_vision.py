# -*- coding: utf-8 -*-
"""画布巡回拼图 · 视觉模块(自包含, 纯函数, 不依赖框架)
坐标全部为游戏客户区 1920x1080 基准。输入图像约定为 RGB ndarray(一条龙截图格式)。
包含: 屏幕状态识别 / 格子数探测 / 碎片归属匹配 / 最少交换计划。
"""
import cv2
import numpy as np

BOARD = (1012, 197, 1828, 1008)      # 拼盘外框区域(3x3/4x4/5x5/6x6 共用)
SR = (940, 110, 1910, 1085)          # 原图视图里的模板搜索区
NS = (3, 4, 5, 6)                    # 拼格规格
INSET = 0.08                         # 拼块采样内收比例(避开网格线和圆角)

LEVEL_CARDS = [(1430, 275 + 154 * i) for i in range(5)]     # 关卡选择页 5 张卡片中心
LEVEL_BADGE_Y = [313 + 154 * i for i in range(5)]           # 每张卡 1/2/3 徽章行中心 y
LEVEL_BADGE_X = (1585, 1845)                                # 徽章区 x 范围
PIECE_TABS = [(1410, 108), (1580, 108), (1748, 108)]        # 拼图页 3 个 PIECE 页签中心
BACK_ARROW = (115, 60)                                      # 左上返回箭头
CLEAR_POS = (960, 150)                                      # 盘外安全点(清除选中态)
IMG_BTN = (906, 945)                                        # 橙色 IMAGE 按钮(拼图视图)
PUZ_BTN = (890, 945)                                        # 蓝色 PUZZLE 按钮(原图视图)
RESET_BTN = (906, 846)                                      # 紫色 RESET 按钮(完成后重洗)
IMG_BTN_RECT = (836, 900, 980, 992)
PUZ_BTN_RECT = (814, 900, 980, 992)
TAB_SLOT_ACTIVE = (1330, 1490, 1495, 1655, 1660, 1820)      # 页签激活黄块 x 区间(成对)


def is_orange(p):
    r, g, b = int(p[0]), int(p[1]), int(p[2])   # RGB (一条龙截图为 RGB)
    return r >= 185 and 120 <= g <= 215 and b <= 125


def is_blue(p):
    r, g, b = int(p[0]), int(p[1]), int(p[2])
    return 25 <= r <= 115 and 65 <= g <= 150 and 145 <= b <= 235


def is_green(p):
    r, g, b = int(p[0]), int(p[1]), int(p[2])
    return g > 150 and r < 120 and b < 120 and g - r > 60 and g - b > 60


def is_tab_yellow(p):
    r, g, b = int(p[0]), int(p[1]), int(p[2])
    return r > 200 and g > 170 and b < 110


def _rect_ratio(img, rect, test):
    h, w = img.shape[:2]
    x0, y0 = max(0, int(rect[0])), max(0, int(rect[1]))
    x1, y1 = min(w - 1, int(rect[2])), min(h - 1, int(rect[3]))
    cnt = total = 0
    for yy in range(y0, y1, 4):
        for xx in range(x0, x1, 4):
            total += 1
            if test(img[yy, xx]):
                cnt += 1
    return cnt / max(1, total)


def view_state(img):
    """'puzzle'=拼图视图 / 'image'=原图视图 / None"""
    if _rect_ratio(img, IMG_BTN_RECT, is_orange) > 0.08:
        return 'puzzle'
    if _rect_ratio(img, PUZ_BTN_RECT, is_blue) > 0.08:
        return 'image'
    return None


def at_puzzle_screen(img):
    return view_state(img) is not None


def at_level_page(img):
    if at_puzzle_screen(img):
        return False
    rect = (LEVEL_BADGE_X[0], LEVEL_BADGE_Y[0] - 25, LEVEL_BADGE_X[1], LEVEL_BADGE_Y[-1] + 25)
    return _rect_ratio(img, rect, is_green) > 0.005


def level_done_flags(img):
    return [(_rect_ratio(img, (LEVEL_BADGE_X[0], by - 24, LEVEL_BADGE_X[1], by + 24), is_green) > 0.01)
            for by in LEVEL_BADGE_Y]


def active_tab_index(img):
    """当前激活 PIECE 页签(0/1/2), 未识别返回 None"""
    h, w = img.shape[:2]
    xs = [x for y in range(60, 160, 3) for x in range(1150, 1900, 3)
          if is_tab_yellow(img[y, x])]
    if len(xs) < 20:
        return None
    cx = (min(xs) + max(xs)) / 2
    slots = [(1330, 1490), (1495, 1655), (1660, 1820)]
    for i, (a, b) in enumerate(slots):
        if a - 30 <= cx <= b + 30:
            return i
    return None


def active_tab_completed(img):
    """当前激活页签是否已有绿勾(游戏注册的完成标记, 完成后持久存在)。
    返回 True/False; 页签未识别返回 None。"""
    idx = active_tab_index(img)
    if idx is None:
        return None
    b = (1330, 1490, 1495, 1655, 1660, 1820)[idx * 2 + 1]
    return _rect_ratio(img, (b - 75, 70, b - 10, 115), is_green) > 0.02


def cut_cells(img, box=BOARD, n=4, inset=INSET):
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / n, (y1 - y0) / n
    out = []
    for r in range(n):
        for c in range(n):
            ax0 = int(x0 + c * cw + cw * inset); ay0 = int(y0 + r * ch + ch * inset)
            ax1 = int(x0 + (c + 1) * cw - cw * inset); ay1 = int(y0 + (r + 1) * ch - ch * inset)
            out.append(img[ay0:ay1, ax0:ax1])
    return out


def cell_center(k, n, box=BOARD):
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / n, (y1 - y0) / n
    return (x0 + (k % n + 0.5) * cw, y0 + (k // n + 0.5) * ch)


def match_by_template(board, ref, n):
    cnt = n * n
    cwb, chb = (BOARD[2] - BOARD[0]) / n, (BOARD[3] - BOARD[1]) / n
    ix, iy = int(cwb * INSET), int(chb * INSET)
    rg = cv2.cvtColor(ref[SR[1]:SR[3], SR[0]:SR[2]], cv2.COLOR_BGR2GRAY)
    hits = []
    for c in cut_cells(board, BOARD, n):
        t = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
        m = cv2.matchTemplate(rg, t, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(m)
        hits.append((loc[0] + SR[0] - ix, loc[1] + SR[1] - iy, score))
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
    if sorted(perm) != list(range(cnt)):
        return None, 0.0
    return perm, float(np.mean([h[2] for h in hits]))


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


def match_by_cells(board, ref, n):
    bc = cut_cells(board, BOARD, n)
    rc = cut_cells(ref, BOARD, n)
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


def detect_grid(board, ref):
    """探测格子数(3x3/4x4/5x5/6x6)并给出归属排列, 返回 (n, perm, score, method)"""
    best = None
    for n in NS:
        perm, score = match_by_template(board, ref, n)
        if perm is not None and (best is None or score > best[2]):
            best = (n, perm, score, '模板匹配')
    if best is not None:
        return best
    best = None
    for n in NS:
        perm, score = match_by_cells(board, ref, n)
        if best is None or score > best[2]:
            best = (n, perm, score, '逐格比对')
    return best


def solve_perm(perm):
    """perm[i]=j: 格i上是属于格j的拼块 -> 交换序列[(from,to)]"""
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


def cells_diff(pre, post, a, b, n):
    pa, pb = cut_cells(pre, BOARD, n), cut_cells(post, BOARD, n)
    d = 0.0
    for k in (a, b):
        h = min(pa[k].shape[0], pb[k].shape[0]); w = min(pa[k].shape[1], pb[k].shape[1])
        d += float(np.abs(pa[k][:h, :w].astype(int) - pb[k][:h, :w].astype(int)).mean())
    return d / 2
