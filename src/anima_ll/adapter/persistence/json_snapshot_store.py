import json
from dataclasses import asdict
from pathlib import Path

from anima_ll.domain.model.individual import IndividualSnapshot


class JsonSnapshotStore:
    """個体のスナップショットを JSON で保存する。実行基盤の状態は保存しない。"""

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: IndividualSnapshot) -> None:
        text = json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)
        (self._dir / f"{snapshot.individual_id}-pulse{snapshot.pulse:08d}.json").write_text(
            text, encoding="utf-8"
        )
        (self._dir / f"{snapshot.individual_id}-latest.json").write_text(text, encoding="utf-8")

    def load_latest(self) -> IndividualSnapshot | None:
        candidates = sorted(self._dir.glob("*-latest.json"))
        if not candidates:
            return None
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
        return IndividualSnapshot(**data)
