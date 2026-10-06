from collections.abc import Sequence

from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import ComponentId
from anima_ll.domain.port.effector import Effector


class EffectorDispatcher:
    """効果器宛ての Delta を該当する Effector に渡す。何を言うべきかは判断しない。"""

    def __init__(self, effectors: Sequence[Effector]) -> None:
        self._effectors: dict[ComponentId, Effector] = {e.effector_id: e for e in effectors}

    def knows(self, effector_id: ComponentId) -> bool:
        return effector_id in self._effectors

    async def dispatch(self, deltas: Sequence[StateDelta]) -> None:
        for delta in deltas:
            await self._effectors[delta.target_id].execute(delta)
