# -*- coding: utf-8 -*-
"""画布巡回拼图 · 输入模块(自包含)
用实测验证过的手势操作游戏:
- 点击 = SetCursorPos + mouse_event(按钮类 UI 响应正常)
- 拖拽 = SendInput 绝对坐标移动 + 按下长停 2.5s(拾取动画) + 缓慢移动 + 停 + 抬起
  (游戏的拾取动画约需 2 秒; 普通快速拖拽会被判定无效弹回)
- 坐标为客户区 1920x1080 基准, 按实际客户区尺寸自动缩放
宿主进程必须与管理员权限运行的游戏同级别(OneDragon 启动器/标准 E2E 均满足)。
"""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.windll.user32
PUL = ctypes.POINTER(ctypes.c_ulong)

BASE_W, BASE_H = 1920, 1080


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", PUL))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", PUL))


class _U(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT))


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


IN_MOUSE = 0
MOVE, ABS, LDOWN, LUP = 0x1, 0x8000, 0x2, 0x4
PICK_HOLD = 2.5
MOVE_STEPS, MOVE_ITV = 24, 0.05
END_HOLD = 0.6


def _mi(dx=0, dy=0, flags=0):
    m = MOUSEINPUT(int(dx), int(dy), 0, flags, 0, None)
    inp = INPUT()
    inp.type = IN_MOUSE
    inp.mi = m
    return inp


def _send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _si_move_abs(x, y):
    ax = int(x * 65535 / max(1, user32.GetSystemMetrics(0) - 1))
    ay = int(y * 65535 / max(1, user32.GetSystemMetrics(1) - 1))
    _send(_mi(ax, ay, MOVE | ABS))


def find_game():
    return user32.FindWindowW(None, '绝区零')


def client_info():
    """返回 (ox, oy, cw, ch) 游戏客户区屏幕坐标与尺寸; 找不到窗口返回 None"""
    hwnd = find_game()
    if not hwnd:
        return None
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
        time.sleep(0.4)
    r = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(r))
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y, r.right, r.bottom


def _scaled(x, y):
    info = client_info()
    if info is None:
        raise RuntimeError('未找到游戏窗口「绝区零」')
    ox, oy, cw, ch = info
    return (int(ox + x * cw / BASE_W), int(oy + y * ch / BASE_H))


def click_client(x, y):
    """点击客户区 1920x1080 基准坐标"""
    sx, sy = _scaled(x, y)
    user32.SetCursorPos(sx, sy)
    time.sleep(0.06)
    user32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(4, 0, 0, 0, 0)


def drag_client(x0, y0, x1, y1):
    """中心点到中心点的拼块拖拽手势"""
    sx0, sy0 = _scaled(x0, y0)
    sx1, sy1 = _scaled(x1, y1)
    _si_move_abs(sx0, sy0)
    time.sleep(0.2)
    _send(_mi(0, 0, LDOWN))
    time.sleep(PICK_HOLD)
    for i in range(1, MOVE_STEPS + 1):
        _si_move_abs(sx0 + (sx1 - sx0) * i / MOVE_STEPS, sy0 + (sy1 - sy0) * i / MOVE_STEPS)
        time.sleep(MOVE_ITV)
    time.sleep(END_HOLD)
    _send(_mi(0, 0, LUP))
    time.sleep(0.3)
