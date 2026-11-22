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
from zzz_od.context.zzz_context import ZContext
from zzz_od.application.zzz_application import ZApplication

from . import drift_canvas_jigsaw_const
from . import jigsaw_input as ji
from . import jigsaw_vision as jv
from .zzz_compat import factory_record_kwargs


class DriftCanvasJigsawApp(ZApplication):

    def __init__(self, ctx: ZContext):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=drift_canvas_jigsaw_const.APP_ID,
            op_name=drift_canvas_jigsaw_const.APP_NAME,
            **factory_record_kwargs(),
        )

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
        return self.round_retry(status='not_jigsaw', wait=2)

    @node_from(from_name='识别界面', status='level')
    @node_from(from_name='切下一关', status='level_page')
    @operation_node(name='选择关卡', node_max_retry_times=10)
    def pick_level(self) -> OperationRoundResult:
        flags = jv.level_done_flags(self.ctx.controller.get_screenshot())
        for i, f in enumerate(flags):
            if not f:
                print(f'[拼图] 进入第 {i + 1} 关')
                ji.click_client(*jv.LEVEL_CARDS[i])
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

    def _solve_board_impl(self) -> str:
        """解当前显示的一盘。返回 solved / already / failed"""
        shot = self.ctx.controller.get_screenshot()
        vs = jv.view_state(shot)
        if vs is None:
            print('[拼图] 未识别到拼图界面')
            return 'failed'
        if jv.active_tab_completed(shot) is True:
            print('[拼图] 当前页签已有绿勾(已完成), 跳过')
            return 'already'
        if vs == 'image':
            ji.click_client(*jv.PUZ_BTN)
            time.sleep(1.4)
        # 清掉可能处于选中/拿起状态的拼块
        ji.click_client(*jv.CLEAR_POS)
        time.sleep(0.6)
        board = self.ctx.controller.get_screenshot()
        ji.click_client(*jv.IMG_BTN)      # 切原图视图抓参考
        time.sleep(1.5)
        ref = self.ctx.controller.get_screenshot()
        ji.click_client(*jv.PUZ_BTN)      # 切回拼图视图
        time.sleep(1.4)
        board = self.ctx.controller.get_screenshot()

        n, perm, score, method = jv.detect_grid(board, ref)
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
                ax, ay = jv.cell_center(a, n)
                bx, by = jv.cell_center(b, n)
                pre = self.ctx.controller.get_screenshot()
                ji.drag_client(ax, ay, bx, by)
                post = self.ctx.controller.get_screenshot()
                if jv.cells_diff(pre, post, a, b, n) > 6:
                    print(f'[拼图]   [{k + 1}/{len(swaps)}] 格{a}->格{b} 完成')
                else:
                    print(f'[拼图]   [{k + 1}/{len(swaps)}] 格{a}->格{b} 未生效, 重试')
                    time.sleep(0.8)
                    ji.drag_client(bx, by, ax, ay)
            board = self.ctx.controller.get_screenshot()
            time.sleep(2.0)  # 若本盘完成, 等完成动画+重洗盘稳定
            board = self.ctx.controller.get_screenshot()
            # 完成的可靠信号是页签绿勾(游戏会自动重洗完成的盘, 盘面复原判定会输给重洗)
            if jv.active_tab_completed(board) is True:
                print(f'[拼图] ★ 检测到页签绿勾, 本盘完成! (共 {rounds} 轮)')
                return 'solved'
            n2, perm, score2, _ = jv.detect_grid(board, ref)
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
        tab = jv.active_tab_index(img)
        if tab is not None and tab < 2:
            target = tab + 1
            print(f'[拼图] 切到 PIECE {target + 1}')
            for i in range(4):
                ji.click_client(*jv.PIECE_TABS[target])
                time.sleep(1.5 + i * 1.2)
                if jv.active_tab_index(self.ctx.controller.get_screenshot()) == target:
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
