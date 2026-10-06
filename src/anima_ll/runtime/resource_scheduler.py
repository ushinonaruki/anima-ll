from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from anima_ll.domain.model.claim import ComputeClaim
from anima_ll.domain.model.identifiers import ResourceClass, UnitId


@dataclass(frozen=True)
class ClaimEntry:
    unit_id: UnitId
    claim: ComputeClaim


@dataclass(frozen=True)
class SchedulingDecision:
    accepted: tuple[ClaimEntry, ...]
    rejected: tuple[ClaimEntry, ...]
    tie_broken: tuple[ResourceClass, ...]
    """容量の境目で同じ強さの claim が並び、unit_id 順で決めた資源。"""


class ResourceScheduler:
    """Resource Class ごとに、空き容量の分だけ claim を強い順に採択する。

    見るのは claim の数値だけ。Unit の重要度や中身は見ない。Unit ごとの補正もしない。

    同じ強さのときは、Pulse ごとに順番を回す（決定論的で意味を持たない）。
    unit_id の辞書順で固定すると、同値が続いたときに特定の Unit が常に勝ち続ける
    偏りが生じることが L0 で確認されたため。
    """

    def select(
        self,
        entries: Sequence[ClaimEntry],
        free_capacity: Mapping[ResourceClass, int],
        pulse: int = 0,
    ) -> SchedulingDecision:
        by_class: dict[ResourceClass, list[ClaimEntry]] = defaultdict(list)
        for entry in entries:
            by_class[entry.claim.resource_class].append(entry)

        accepted: list[ClaimEntry] = []
        rejected: list[ClaimEntry] = []
        tie_broken: list[ResourceClass] = []
        for resource_class in sorted(by_class):
            candidates = by_class[resource_class]
            ids = sorted(e.unit_id for e in candidates)
            n = len(ids)
            ordered = sorted(
                candidates,
                key=lambda e: (-e.claim.strength, (ids.index(e.unit_id) - pulse) % n),
            )
            capacity = max(0, free_capacity.get(resource_class, 0))
            accepted.extend(ordered[:capacity])
            rejected.extend(ordered[capacity:])
            if 0 < capacity < len(ordered):
                if ordered[capacity - 1].claim.strength == ordered[capacity].claim.strength:
                    tie_broken.append(resource_class)
        return SchedulingDecision(tuple(accepted), tuple(rejected), tuple(tie_broken))
