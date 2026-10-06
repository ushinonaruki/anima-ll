from anima_ll.domain.model.identifiers import ComponentId
from anima_ll.domain.model.manifest import NeuroarchitectureManifest, ProjectionSpec


class ProjectionRouter:
    """出力路から出た信号の到達先を、Manifest の配線だけで決める。宛先を選ばない。"""

    def __init__(self, manifest: NeuroarchitectureManifest) -> None:
        self._manifest = manifest

    def route(self, source_id: ComponentId, port: str) -> tuple[ProjectionSpec, ...]:
        return self._manifest.projections_from(source_id, port)
