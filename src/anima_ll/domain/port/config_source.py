from typing import Protocol

from anima_ll.domain.model.environment import EnvironmentSpec
from anima_ll.domain.model.individual import BirthState
from anima_ll.domain.model.manifest import NeuroarchitectureManifest


class NeuroarchitectureSource(Protocol):
    def load(self) -> NeuroarchitectureManifest: ...


class EnvironmentSource(Protocol):
    def load(self) -> EnvironmentSpec: ...


class BirthStateSource(Protocol):
    def load(self) -> BirthState: ...
