# zzzod-plugin-drift-canvas-jigsaw

绝区零一条龙第三方插件：梦现追影「画布巡回」拼图活动全自动通关。

## 功能
- 自动识别屏幕状态：关卡选择页 / 拼图盘 / 原图预览
- 自动探测格子规格：3x3 / 4x4 / 5x5 / 6x6
- 模板匹配求碎片归属（逐格比对兜底），计算最少交换步骤
- 中心点长按拖拽手势（拾取动画 2.5s），逐拖校验失败自动重试
- 页签绿勾判定完成（规避完成后自动重洗盘的竞态）
- 自动切页签、返回关卡页、进入下一关，直到五关全清

## 前置条件
游戏已停留在拼图活动的「关卡选择页」或「拼图盘」界面。

## 运行
一条龙 GUI 应用列表选择「画布巡回拼图」运行，或独立应用 CLI：
```
.venv/Scripts/python.exe -u run_single_app.py -a drift_canvas_jigsaw
```

## 模块
- `jigsaw_vision.py` 视觉判定（纯函数，可独立复用）
- `jigsaw_input.py` 游戏输入手势（自包含 SendInput，宿主需提权）
- `drift_canvas_jigsaw_app.py` 状态机编排
