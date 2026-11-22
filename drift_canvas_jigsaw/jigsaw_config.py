# -*- coding: utf-8 -*-
from one_dragon.base.operation.application.application_config import ApplicationConfig


class DriftCanvasJigsawConfig(ApplicationConfig):

    def __init__(self, instance_idx: int, group_id: str):
        ApplicationConfig.__init__(
            self,
            'drift_canvas_jigsaw',
            instance_idx=instance_idx,
            group_id=group_id,
        )
