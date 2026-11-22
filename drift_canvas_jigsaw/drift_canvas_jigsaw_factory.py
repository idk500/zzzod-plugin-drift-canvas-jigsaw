# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import TYPE_CHECKING

from one_dragon.base.operation.application.application_config import ApplicationConfig
from one_dragon.base.operation.application.application_factory import ApplicationFactory
from one_dragon.base.operation.application_base import Application
from . import drift_canvas_jigsaw_const
from .drift_canvas_jigsaw_app import DriftCanvasJigsawApp
from .jigsaw_config import DriftCanvasJigsawConfig

if TYPE_CHECKING:
    from zzz_od.context.zzz_context import ZContext


class DriftCanvasJigsawFactory(ApplicationFactory):

    def __init__(self, ctx: ZContext):
        ApplicationFactory.__init__(self, drift_canvas_jigsaw_const)
        self.ctx: ZContext = ctx

    def create_application(self, instance_idx: int, group_id: str) -> Application:
        return DriftCanvasJigsawApp(self.ctx)

    def create_config(
        self, instance_idx: int, group_id: str
    ) -> ApplicationConfig:
        return DriftCanvasJigsawConfig(
            instance_idx=instance_idx,
            group_id=group_id,
        )
