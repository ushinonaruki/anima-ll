import json
from pathlib import Path

from anima_ll.domain.model.runtime_event import RuntimeEvent


class JsonlEventLog:
    """来歴ログを JSON Lines で追記する。"""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self._path.open("a", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: RuntimeEvent) -> None:
        record = {"type": event.type, "pulse": event.pulse, **event.data}
        self._file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()
