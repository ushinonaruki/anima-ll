from typing import Protocol

from anima_ll.domain.model.manifest import NeuroarchitectureManifest


class ManifestSource(Protocol):
    def load(self) -> NeuroarchitectureManifest: ...
