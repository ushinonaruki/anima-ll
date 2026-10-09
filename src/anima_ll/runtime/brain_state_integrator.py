from collections.abc import Sequence

from anima_ll.domain.model.activity import Drive
from anima_ll.domain.model.brain_state import BrainState
from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import PulseNumber


class BrainStateIntegrator:
    """Pulse の境界で、確定した Delta と駆動を BrainState に反映する。

    期限切れの Delta は機械的に取り除く。「重要だから残す」という判断はしない。
    駆動は次の Pulse にだけ届くので、この Pulse に成立したものに置き換える。
    """

    def integrate(
        self,
        current: BrainState,
        deltas: Sequence[StateDelta],
        drives: Sequence[Drive],
        pulse: PulseNumber,
    ) -> BrainState:
        next_pulse = pulse + 1
        alive = tuple(d for d in current.deltas if d.expires_after_pulse >= next_pulse)
        return BrainState(deltas=alive + tuple(deltas), drives=tuple(drives))
