from dataclasses import dataclass

from anima_ll.domain.model.identifiers import ComponentId, JsonValue


@dataclass(frozen=True)
class SensoryEvent:
    """Receptor（Environment）が外界を受け取った、という出来事。

    成立させるのは Receptor で、Runtime ではない（活動の伝達 仕様 §4.1）。
    Runtime はこれを接続に沿って感覚の駆動として運ぶ。中身（material）を添えるかどうかも
    Receptor が決める。None なら中身はなく、駆動だけが届く。
    """

    receptor_id: ComponentId
    material: JsonValue | None = None
