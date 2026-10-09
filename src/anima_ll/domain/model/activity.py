"""活動の伝達（活動の伝達・感覚の駆動・中身の運搬の境界 仕様 v0.2）。

Unit を外から動かすのは、送り手の側で成立した出来事だけ（C2）：
- Unit の ActivityEvent（Neuroarchitecture で成立）
- Receptor の SensoryEvent（Environment で成立）
Runtime はどちらも同じ運び方で、接続に沿って Drive として受け手に届ける（§3.3）。
Delta（中身）は駆動しない（C1）。
"""

from dataclasses import dataclass

from anima_ll.domain.model.identifiers import ComponentId, PulseNumber, UnitId


@dataclass(frozen=True)
class ActivityEvent:
    """Unit が発火した、という Neuroarchitecture の中の出来事。

    Unit の力学が発火を返した時点で、Unit 自身が作る。中身も強さも持たない。
    出力の部品が何を出すかとは独立に成立する。
    """

    unit_id: UnitId
    pulse: PulseNumber


@dataclass(frozen=True)
class Drive:
    """接続を通って受け手に届く駆動。

    weight は、伝達が成立した Pulse の接続の重みを凍結したもの（接続の状態 仕様 §5）。
    接続の状態そのものではなく、「この伝達が成立した時点では、この強さだった」という記録。
    """

    source_id: ComponentId
    target_id: UnitId
    weight: float
    created_pulse: PulseNumber
