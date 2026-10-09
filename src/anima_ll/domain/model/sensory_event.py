from dataclasses import dataclass

from anima_ll.domain.model.identifiers import ComponentId, JsonValue, PulseNumber


@dataclass(frozen=True)
class SensoryEvent:
    """Receptor（Environment）が外界を受け取った、という出来事。

    成立させるのは Receptor で、Runtime ではない（活動の伝達 仕様 §4.1）。
    Runtime はこれを接続に沿って感覚の駆動として運ぶ。中身（material）を添えるかどうかも
    Receptor が決める。None なら中身はなく、駆動だけが届く。

    pulse は、この出来事が成立した Pulse。出来事に Pulse を書き込むのは Receptor だが、
    **成立の Pulse は、その Receptor が drain された今の Pulse に限る**（契約）。
    過去の Pulse を申告する遅れた出来事は、今は扱わない（遡って届けることになるため）。
    実世界で取得した時刻と、脳に提示した Pulse を区別したくなったら、別の情報として設計する。
    """

    receptor_id: ComponentId
    pulse: PulseNumber
    material: JsonValue | None = None
