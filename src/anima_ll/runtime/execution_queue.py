"""実行待ちの列（計算資源境界 仕様 v0.3.1 §2.3・§3.3・§4）。

- 計算資源の種類ごとに、受理した順（intent_seq 順）に並べる
- 容量不足や Unit が計算中であることを理由に、意図を捨てない
- 取り出しは work-conserving：列の先頭から見て、今実行できる最初の意図を渡す。
  同じ Unit の前の意図が実行中で今は実行できない意図は、列から外さずに飛ばす
- 同じ Unit の意図は intent_seq の順に 1 件ずつ（Unit ごとの直列化）
- 上限（Environment の設定。None なら上限なし）に達したら、新しく来た意図を受け付けない（tail-drop）。
  上限は「まだ Worker に渡されていない待ちの意図」の数に対するもので、受理はその Pulse の取り出しより前に行う

これは認知の原理ではなく、参照用の工学的な方針である。意図の中身・強さ・価値は見ない。
"""

from collections.abc import Iterable, Mapping

from anima_ll.domain.model.identifiers import ResourceClass, UnitId
from anima_ll.runtime.compute_intent import ComputeIntent


class ExecutionQueue:
    def __init__(self, capacities: Mapping[ResourceClass, int | None]) -> None:
        self._capacities = dict(capacities)
        self._waiting: dict[ResourceClass, list[ComputeIntent]] = {rc: [] for rc in self._capacities}

    def admit(self, intent: ComputeIntent) -> bool:
        """受理したら True。上限に達していて受け付けなかったら False（tail-drop）。"""
        waiting = self._waiting.setdefault(intent.resource_class, [])
        limit = self._capacities.get(intent.resource_class)
        if limit is not None and len(waiting) >= limit:
            return False
        waiting.append(intent)
        return True

    def take_dispatchable(
        self,
        free_workers: Mapping[ResourceClass, int],
        busy_units: Iterable[UnitId],
    ) -> list[ComputeIntent]:
        """空いた Worker の数だけ、今実行できる意図を intent_seq 順に取り出す。"""
        busy = set(busy_units)
        taken: list[ComputeIntent] = []
        for resource_class in sorted(self._waiting):
            free = max(0, free_workers.get(resource_class, 0))
            remaining: list[ComputeIntent] = []
            for intent in self._waiting[resource_class]:
                if free > 0 and intent.unit_id not in busy:
                    taken.append(intent)
                    busy.add(intent.unit_id)  # 同じ Unit の次の意図は、この計算が終わるまで待つ
                    free -= 1
                else:
                    remaining.append(intent)
            self._waiting[resource_class] = remaining
        return taken

    def waiting(self, resource_class: ResourceClass | None = None) -> tuple[ComputeIntent, ...]:
        if resource_class is not None:
            return tuple(self._waiting.get(resource_class, ()))
        return tuple(i for rc in sorted(self._waiting) for i in self._waiting[rc])
