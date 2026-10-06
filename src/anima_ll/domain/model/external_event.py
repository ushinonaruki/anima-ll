from dataclasses import dataclass

from anima_ll.domain.model.identifiers import ComponentId, JsonValue


@dataclass(frozen=True)
class ExternalEvent:
    """感覚器が受け取った外界からの入力。"""

    receptor_id: ComponentId
    payload: JsonValue
