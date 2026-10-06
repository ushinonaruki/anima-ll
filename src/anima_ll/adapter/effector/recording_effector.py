from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import ComponentId


class RecordingEffector:
    """届いた Delta を記録するだけ。テスト用。"""

    def __init__(self, effector_id: ComponentId) -> None:
        self._effector_id = effector_id
        self.received: list[StateDelta] = []

    @property
    def effector_id(self) -> ComponentId:
        return self._effector_id

    async def execute(self, delta: StateDelta) -> None:
        self.received.append(delta)
