from anima_ll.domain.model.identifiers import ComponentId, is_effector
from anima_ll.domain.model.manifest import NeuroarchitectureManifest, ProjectionSpec


class ProjectionRouter:
    """出力路から出た信号の到達先を、Manifest の配線だけで決める。宛先を選ばない。"""

    def __init__(self, manifest: NeuroarchitectureManifest) -> None:
        self._manifest = manifest

    def route(self, source_id: ComponentId, port: str) -> tuple[ProjectionSpec, ...]:
        """中身（Delta）の到達先。出力路ごと。"""
        return self._manifest.projections_from(source_id, port)

    def route_activity(self, source_id: ComponentId) -> tuple[ProjectionSpec, ...]:
        """駆動の到達先。送り手が Unit でも Receptor でも同じ規則で引く（活動の伝達 仕様 §3.3）。

        発火は Unit 全体の出来事なので、出力路を問わず、その送り手からのすべての接続に伝わる（§6）。
        Effector には届けない（§7：発火を直接行動にする経路を作らない）。
        """
        return tuple(
            p for p in self._manifest.projections
            if p.source_id == source_id and not is_effector(p.target_id)
        )
