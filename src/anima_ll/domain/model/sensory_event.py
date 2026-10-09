from dataclasses import dataclass

from anima_ll.domain.model.identifiers import ComponentId, JsonValue, PulseNumber


@dataclass(frozen=True)
class SensoryEvent:
    """Receptor（Environment）が外界を受け取った、という出来事。

    成立させるのは Receptor で、Runtime ではない（活動の伝達 仕様 §4.1）。
    Runtime はこれを接続に沿って感覚の駆動として運ぶ。中身（material）を添えるかどうかも
    Receptor が決める。None なら中身はなく、駆動だけが届く。

    pulse は、この出来事が成立した Pulse。Pulse の番号は Runtime が drain に機械的に渡すが、
    出来事にどの Pulse を付けるか（成立の時刻）を確定するのは Receptor である（Runtime の収集の時刻と混ぜない）。
    """

    receptor_id: ComponentId
    pulse: PulseNumber
    material: JsonValue | None = None
