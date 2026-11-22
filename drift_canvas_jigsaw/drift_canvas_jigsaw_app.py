# -*- coding: utf-8 -*-
"""画布巡回拼图 · 应用
状态机: 识别界面 → (关卡页: 选未完成关卡) → 解当前盘 → 切下一页签/返回关卡页 → ... → 全部完成
前置条件: 游戏已停留在「梦现追影画布」拼图活动的关卡选择页或拼图盘界面。
解耦说明: 本应用只做流程编排; 视觉判定在 jigsaw_vision, 游戏输入在 jigsaw_input,
两模块自包含, 可独立复用。
"""
import time

from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.base.operation.operation import Operation
from zzz_od.context.zzz_context import ZContext
from zzz_od.application.zzz_application import ZApplication

from . import drift_canvas_jigsaw_const
from . import jigsaw_input as ji
from . import jigsaw_vision3 as jv
from .zzz_compat import factory_record_kwargs




class SmartEnterGame(Operation):
    """智能进入游戏(无人值守核心):
    1. 游戏窗口已存在 -> 直接走登录/进入流程(已在世界则快速通过)
    2. 不存在 -> 以 CREATE_BREAKAWAY_FROM_JOB 启动游戏 exe(脱离宿主 Job,
       宿主/链退出不再连坐杀游戏), 轮询窗口就绪(最长 5 分钟) -> 登录/进入流程
    非冻结 python 下 breakaway 生效; 这是与打包 launcher 的关键差异。"""

    def __init__(self, ctx: ZContext):
        self.ctx = ctx
        Operation.__init__(self, ctx, op_name='智能进入游戏', need_check_game_win=False)

    @operation_node(name='检测并启动游戏', is_start_node=True, node_max_retry_times=2)
    def check_and_open(self) -> OperationRoundResult:
        import os
        import subprocess
        import sys as _sys

        def window_ready():
            info = ji.client_info()
            return info is not None and info[2] > 0

        if window_ready():
            print('[拼图] 游戏窗口已存在')
        else:
            game_path = self.ctx.game_account_config.game_path
            if not game_path:
                return self.round_fail('未配置游戏路径, 请在一条龙[账户管理]设置')
            d = os.path.dirname(game_path)
            exe = os.path.basename(game_path)
            cmd = f'cmd /c "start "" /d "{d}" "{exe}" & exit"'
            flags = 0
            if not getattr(_sys, 'frozen', False):
                flags = subprocess.CREATE_BREAKAWAY_FROM_JOB  # 逃离宿主 Job
            print(f'[拼图] breakaway 启动游戏: {exe}')
            subprocess.Popen(cmd, shell=True, creationflags=flags)
            ready = False
            for i in range(60):
                time.sleep(5)
                if window_ready():
                    print(f'[拼图] 游戏窗口就绪 ({(i + 1) * 5}s)')
                    ready = True
                    break
            if not ready:
                return self.round_fail('游戏窗口 5 分钟未就绪')
        time.sleep(2)
        from zzz_od.operation.enter_game.enter_game import EnterGame
        op = EnterGame(self.ctx)
        return self.round_by_op_result(op.execute())

class DriftCanvasJigsawApp(ZApplication):

    def __init__(self, ctx: ZContext):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=drift_canvas_jigsaw_const.APP_ID,
            op_name=drift_canvas_jigsaw_const.APP_NAME,
            op_to_enter_game=SmartEnterGame(ctx),
            **factory_record_kwargs(),
        )
        self._nav_step: int = 0
        self._drag_delay: float = 0.45      # 当前拖前延时(自适应)
        self._delay_good: float = 0.45      # 最后一次可用的延时

    @operation_node(name='识别界面', is_start_node=True, node_max_retry_times=60)
    def wait_ui(self) -> OperationRoundResult:
        img = self.ctx.controller.get_screenshot()
        if img is None:
            return self.round_retry(status='no_screenshot', wait=1)
        vs = jv.view_state(img)
        if vs == 'puzzle':
            return self.round_success(status='puzzle')
        if vs == 'image':
            ji.click_client(*jv.PUZ_BTN)  # 原图视图 → 回拼图视图
            return self.round_retry(status='back_from_image', wait=1.5)
        if jv.at_level_page(img):
            return self.round_success(status='level')
        # not_jigsaw: 大世界或未知界面 -> OCR 导航到活动入口(每步落盘 .debug/jigsaw_nav/)
        self._nav_step += 1
        tag = f'r{self._nav_step}'
        # 1) 优先 OCR 找活动入口/前往按钮
        for kw in ('画布巡回', '梦现追影', '前往'):
            r = self.round_by_ocr_and_click(img, kw)
            if r.is_success:
                print(f'[拼图] 导航: OCR 点击「{kw}」')
                self._nav_dump(tag + '_ocr_' + kw)
                return self.round_retry(status='nav_ocr', wait=2.5)
        # 2) 大世界右上角 TV 图标(带 New 角标) = 活动入口
        self._nav_click_and_dump(tag + '_tv', jv.TV_BTN)
        return self.round_retry(status='not_jigsaw', wait=2.5)

    @node_from(from_name='识别界面', status='level')
    @node_from(from_name='切下一关', status='level_page')
    @operation_node(name='选择关卡', node_max_retry_times=10)
    def pick_level(self) -> OperationRoundResult:
        rows = jv.level_rows(self.ctx.controller.get_screenshot())
        for i, r in enumerate(rows):
            if not r['done']:
                pos = jv.pick_click_pos(r)
                print(f'[拼图] 进入第 {i + 1} 关 (行 y={r[chr(121)]})')
                ji.click_client(*pos)
                return self.round_success(status='entered', wait=2)
        return self.round_success(status='all_done')

    @node_from(from_name='选择关卡', status='all_done')
    @operation_node(name='全部完成')
    def all_done(self) -> OperationRoundResult:
        print('[拼图] ★★★ 五个关卡全部通关 ★★★')
        return self.round_success()

    @node_from(from_name='识别界面', status='puzzle')
    @node_from(from_name='选择关卡', status='entered')
    @node_from(from_name='切下一关', status='next_piece')
    @operation_node(name='解当前盘', node_max_retry_times=2)
    def solve_board(self) -> OperationRoundResult:
        result = self._solve_board_impl()
        if result in ('solved', 'already'):
            return self.round_success(status='board_solved')
        return self.round_fail(status='solve_failed')


    def _nav_click_and_dump(self, tag, pos, wait=2.0):
        """导航探路: 点击 + 落盘截图(无人值守 E2E 的眼睛)"""
        import os
        ji.click_client(*pos)
        time.sleep(wait)
        try:
            img = self.ctx.controller.get_screenshot()
            d = r'E:\Z1D\app\.debug\jigsaw_nav'
            os.makedirs(d, exist_ok=True)
            import cv2 as _cv2
            _cv2.imwrite(os.path.join(d, f'nav_{tag}.png'), img)
        except Exception as e:
            print(f'[拼图] nav dump 失败: {e}')

    def _nav_dump(self, tag):
        """导航过程截图落盘(无人值守 E2E 的眼睛)"""
        import cv2 as _cv2
        import os
        try:
            img = self.ctx.controller.get_screenshot()
            d = os.path.join(r'E:\Z1Dpp\.debug', 'jigsaw_nav')
            os.makedirs(d, exist_ok=True)
            _cv2.imwrite(os.path.join(d, f'nav_{tag}.png'), img)
        except Exception as e:
            print(f'[拼图] nav dump 失败: {e}')

    def _nav_click_and_dump(self, tag, pos, wait=2.0):
        """导航探路: 点击 + 落盘"""
        ji.click_client(*pos)
        time.sleep(wait)
        self._nav_dump(tag)

    def _solve_board_impl(self) -> str:
        """解当前显示的一盘。返回 solved / already / failed"""
        shot = self.ctx.controller.get_screenshot()
        board = jv.find_board(shot)
        if board is None:
            print('[拼图] 未检测到拼图盘')
            return 'failed'
        idx0 = jv.active_tab_index_v3(shot, board)
        if jv.active_tab_completed(shot, board, idx0 if idx0 is not None else 0) is True:
            print('[拼图] 当前页签已有绿勾(已完成), 跳过')
            return 'already'
        vs = jv.view_state_v3(shot, board)
        if vs == 'image':
            ji.click_client(*jv.anchor_buttons(board)['puz'])
            time.sleep(1.4)
        # 清掉可能处于选中/拿起状态的拼块
        ji.click_client(*jv.CLEAR_POS)
        time.sleep(0.6)
        board_img = self.ctx.controller.get_screenshot()
        btns = jv.anchor_buttons(jv.find_board(board_img) or board)
        ji.click_client(*btns['img'])     # 切原图视图抓参考
        time.sleep(1.5)
        ref = self.ctx.controller.get_screenshot()
        ji.click_client(*btns['puz'])     # 切回拼图视图
        time.sleep(1.4)
        board_img = self.ctx.controller.get_screenshot()
        box = jv.find_board(board_img) or board

        n, perm, score, method = jv.detect_grid(board_img, ref, box)
        print(f'[拼图] 识别完成: {n}x{n} 共 {n * n} 块 ({method}, 平均分 {score:.3f})')
        if perm == list(range(n * n)):
            print('[拼图] 当前盘已复原, 无需操作')
            return 'already'

        rounds = 0
        while rounds < 4:
            rounds += 1
            swaps = jv.solve_perm(perm)
            print(f'[拼图] 第 {rounds} 轮: 需 {len(swaps)} 次交换')
            for k, (a, b) in enumerate(swaps):
                ax, ay = jv.cell_center(a, n, box)
                bx, by = jv.cell_center(b, n, box)
                time.sleep(self._drag_delay)
                pre = self.ctx.controller.get_screenshot()
                ji.drag_client(ax, ay, bx, by)
                post = self.ctx.controller.get_screenshot()
                if jv.cells_diff(pre, post, a, b, n, box) > 6:
                    print(f'[拼图]   [{k + 1}/{len(swaps)}] 格{a}->格{b} 完成 (延时 {self._drag_delay:.2f}s)')
                    self._delay_good = self._drag_delay
                    self._drag_delay = max(0.15, self._drag_delay * 0.85)  # 成功 -> 缩短
                else:
                    print(f'[拼图]   [{k + 1}/{len(swaps)}] 格{a}->格{b} 未生效, 回退延时 {self._delay_good:.2f}s 重试')
                    self._drag_delay = min(2.0, self._delay_good * 1.5)   # 失败 -> 回退最后一次可用值并放宽
                    time.sleep(0.6)
                    ji.drag_client(bx, by, ax, ay)
                    self._drag_delay = self._delay_good
            board_img = self.ctx.controller.get_screenshot()
            time.sleep(2.0)  # 若本盘完成, 等完成动画+重洗盘稳定
            board_img = self.ctx.controller.get_screenshot()
            box2 = jv.find_board(board_img) or box
            chk = jv.active_tab_completed(board_img, box2, jv.active_tab_index_v3(board_img, box2) or 0)
            if chk is True:
                print(f'[拼图] ★ 检测到页签绿勾, 本盘完成! (共 {rounds} 轮)')
                return 'solved'
            n2, perm, score2, _ = jv.detect_grid(board_img, ref, box2)
            if n2 != n:
                print(f'[拼图] 格子数变化 {n}->{n2}')
                n = n2
            if perm == list(range(n * n)):
                print('[拼图] ★ 本盘复原完成!')
                return 'solved'
            print('[拼图] 尚未复原, 继续下一轮')
        print('[拼图] 4 轮后仍未复原')
        return 'failed'

    @node_from(from_name='解当前盘', status='board_solved')
    @operation_node(name='切下一关', node_max_retry_times=2)
    def after_board(self) -> OperationRoundResult:
        time.sleep(2.5)  # 完成动画 + 自动重洗盘, 等待稳定
        img = self.ctx.controller.get_screenshot()
        box = jv.find_board(img)
        tab = jv.active_tab_index_v3(img, box) if box else None
        if tab is not None and tab < 2:
            target = tab + 1
            print(f'[拼图] 切到 PIECE {target + 1}')
            for i in range(4):
                tx = int(box[0] + (target + 0.5) * (box[2] - box[0]) / 3)
                ji.click_client(tx, 108)
                time.sleep(1.5 + i * 1.2)
                b2 = jv.find_board(self.ctx.controller.get_screenshot())
                if b2 and jv.active_tab_index_v3(self.ctx.controller.get_screenshot(), b2) == target:
                    return self.round_success(status='next_piece')
            return self.round_fail(status='tab_switch_failed')
        # tab==2 或未识别 → 返回关卡选择页
        print('[拼图] 本关 3 块完成, 返回关卡选择页')
        for i in range(4):
            ji.click_client(*jv.BACK_ARROW)
            time.sleep(1.8 + i * 1.2)
            if jv.at_level_page(self.ctx.controller.get_screenshot()):
                return self.round_success(status='level_page')
        return self.round_fail(status='back_failed')
