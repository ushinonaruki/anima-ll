from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import JsonValue, PulseNumber, UnitId


@dataclass(frozen=True)
class IndividualSnapshot:
    """個体の保存形式。実行基盤の状態（Worker・キュー・キャッシュ）は含めない。"""

    individual_id: str
    pulse: PulseNumber
    units: dict[UnitId, JsonValue] = field(default_factory=dict)
