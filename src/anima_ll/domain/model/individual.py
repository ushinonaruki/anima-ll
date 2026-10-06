from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import JsonValue, PulseNumber, UnitId


@dataclass(frozen=True)
class BirthState:
    """個体が生まれるときの条件。

    同じ脳の設計図からでも、BirthState が違えば別の個体になる。
    L1 では個体 ID と seed（初期値のばらつきの元）だけを持つ。
    """

    individual_id: str
    seed: int


@dataclass(frozen=True)
class IndividualSnapshot:
    """個体の保存形式。実行基盤の状態（Worker・キュー・キャッシュ）は含めない。"""

    individual_id: str
    pulse: PulseNumber
    units: dict[UnitId, JsonValue] = field(default_factory=dict)
