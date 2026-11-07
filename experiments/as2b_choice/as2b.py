"""AS2b（手がかりの後の二つの行動の選択）の最小の研究用の道具（docs/as2b-minimal-implementation-contract.md の ②a）。

【位置づけ】正式な実験ではない。契約（①、#176）を満たす道具と、その契約テストのためのもの。
Unit の力学・可塑性の規則・確定したパラメータ・Pulse の順序（Core）は変えない。設計図は AS1 と同じく、C0 の設計図に
Effector 1 つと、出力路 `intent` から Effector への投射だけを足したもの（`as1.as1_manifest_raw`）。

部品（契約の方式 1）
- I2Decider：二つの源が共有する I2 の決定の部品。Pulse ごとに両方の源の発火の有無の報告を受け、そろったら対称に決める。
  勝ちが決まったら「翌 Pulse に勝った源の口が出す」を予定する。層 A の記録（契約 §2.8）を持つ。Delta の識別子・世界・
  結果・規則 c を読まない（EC-2）。乱数を使わない（EC-10）
- CompetitionTap：源の Unit を包む競合の口。中の Unit の tick をそのまま呼び、予定があれば意図の提案を 1 つ足し、
  発火の有無を報告する（EC-5・EC-6）
- AS2bWorld：手がかりの予約と、規則 c が指す行動 ID の意図にだけ手がかりの Receptor へ結果を返す規則（WB-1〜WB-9）。
  受けた意図の記録は層 B（Delta の識別子・出どころ・Pulse・行動 ID）
- AS2bEffector：受けた意図の Delta を世界に渡すだけ（選ばない）
- TrialSchedule：手がかりの予定と窓の区間を一つの物から作る（WB-2）。命題 T-4 の条件を組み立ての時に調べる（CT-W2）
- audit：層 A と層 B の外部の突合（CT-E10）。結果は記録と解析にだけ使い、脳にも世界にも戻さない

AS1 の道具（`experiments/as1_closed_loop/as1.py`）から、接続の口の包み・移植・来歴のログ・Σ・再生の予定・Σ の違いを
そのまま使う。
"""

import copy
import importlib.util
import random
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from pathlib import Path

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.bootstrap import Application, build_application
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta, StateDelta
from anima_ll.domain.model.identifiers import (
    ComponentId,
    JsonValue,
    PulseNumber,
    UnitId,
)
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.runtime_event import RuntimeEventType
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_ll.domain.port.cognitive_unit import CognitiveUnit

ROOT = Path(__file__).resolve().parents[2]


def _load_as1():
    spec = importlib.util.spec_from_file_location("as1_tools_for_as2b", ROOT / "experiments" / "as1_closed_loop" / "as1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AS1 = _load_as1()

INTENT_PORT = AS1.INTENT_PORT
EFFECTOR_ID = AS1.EFFECTOR_ID
UNITS = AS1.UNITS
RECEPTOR_OF = AS1.RECEPTOR_OF
PULSE_INTERVAL_SECONDS = AS1.PULSE_INTERVAL_SECONDS
ACTION_IDS = ("A1", "A2")              # 意味の名前を付けない（AI7・EC-9）
TIE = "tie"
NONE = "none"


# ---- 役の割り当て（K2・WB-7） ------------------------------------------------------

@dataclass(frozen=True)
class Roles:
    cue: UnitId              # 手がかりの Unit
    source1: UnitId          # 源 1（行動 A1）
    source2: UnitId          # 源 2（行動 A2）

    @property
    def cue_receptor(self) -> ComponentId:
        return RECEPTOR_OF[self.cue]

    @property
    def source_receptors(self) -> tuple[ComponentId, ComponentId]:
        return RECEPTOR_OF[self.source1], RECEPTOR_OF[self.source2]

    @property
    def action_of(self) -> dict[UnitId, str]:
        return {self.source1: ACTION_IDS[0], self.source2: ACTION_IDS[1]}

    def as_dict(self) -> dict[str, str]:
        return {"cue": self.cue, "source1": self.source1, "source2": self.source2,
                "cue_receptor": self.cue_receptor, "source1_action": ACTION_IDS[0], "source2_action": ACTION_IDS[1]}


def assign_roles(seed: int) -> Roles:
    """個体ごとに、名前で分けた乱数の流れ（Birth State の乱数とは別）で役を割り当てる。"""
    order = list(UNITS)
    random.Random(f"as2b-roles-{seed}").shuffle(order)
    return Roles(*order)


# ---- 予定と窓（WB-2・命題 T-4） ----------------------------------------------------

class ScheduleConflict(ValueError):
    """窓が重なる、または手がかりと結果の予約が重なりうる予定（命題 T-4・CT-W2）。"""


@dataclass(frozen=True)
class TrialSchedule:
    """手がかりの Pulse の列と、窓の区間の列を一つの物から作る（WB-2）。窓 k ＝ [c_k ＋ o, c_k ＋ o ＋ W − 1]。"""

    cues: tuple[PulseNumber, ...]
    offset: int              # o
    length: int              # W

    @classmethod
    def periodic(cls, *, first: int, spacing: int, count: int, offset: int, length: int) -> "TrialSchedule":
        return cls(tuple(first + spacing * k for k in range(count)), offset, length)

    @property
    def windows(self) -> tuple[tuple[int, PulseNumber, PulseNumber], ...]:
        return tuple((k + 1, c + self.offset, c + self.offset + self.length - 1) for k, c in enumerate(self.cues))

    def check(self, delay: int) -> None:
        if self.offset < 0 or self.length < 1:
            raise ScheduleConflict(f"o ＝ {self.offset}、W ＝ {self.length}：o ≥ 0・W ≥ 1 でなければならない")
        if list(self.cues) != sorted(set(self.cues)) or (self.cues and self.cues[0] < 1):
            raise ScheduleConflict("手がかりの Pulse は 1 以上の増える列でなければならない")
        windows = self.windows
        for (_k, _a, b), c_next in zip(windows, self.cues[1:]):
            if c_next < b + delay + 1:
                raise ScheduleConflict(f"c_(k+1) ＝ {c_next} ＜ b_k ＋ L ＋ 1 ＝ {b + delay + 1}（命題 T-4）")
        for (_k, _a, b), (_k2, a2, _b2) in pairwise(windows):
            if a2 <= b:
                raise ScheduleConflict("窓が重なる")

    def last_outcome_pulse(self, delay: int) -> PulseNumber:
        """最後の窓の終わりの決定から出た意図の、結果の刺激の Pulse（b_K ＋ 1 ＋ L − 1）。"""
        return self.windows[-1][2] + delay

    def as_dict(self) -> dict:
        return {"cues": list(self.cues), "offset": self.offset, "length": self.length}


# ---- 出口：I2 の決定の部品と競合の口（EC-1〜EC-10） ------------------------------

class I2Error(RuntimeError):
    """報告の欠け・重複、出す予定の取りこぼし、窓の閉じ損ね（EC-7・CT-E9）。"""


class I2Decider:
    """二つの源が共有する I2 の決定の部品（契約 §2.5）。

    - 読むのは、二つの源の Pulse ごとの発火の有無と Pulse の番号と、窓の区間の写しだけ（EC-2）
    - Pulse t の決定は、二つの報告がそろった後に、(f_1(t), f_2(t)) の対称な関数として行う（EC-3）
    - 窓の中の最初の「発火のある Pulse」で、単独なら勝ち、両方なら引き分けとして窓を閉じる。発火がないまま b_k を
      過ぎたら意図なしで閉じる。閉じた窓と窓の外の発火からは何も生まれない（EC-4）
    - 勝ちは「Pulse t ＋ 1 に、勝った源の口が出す」として予定する（EC-5）
    - 層 A の記録（契約 §2.8）を持つ。Delta の識別子は持たない（EC-7）
    """

    def __init__(self, windows: Sequence[tuple[int, PulseNumber, PulseNumber]], action_of: Mapping[UnitId, str]) -> None:
        if len(action_of) != 2 or sorted(action_of.values()) != sorted(ACTION_IDS):
            raise ValueError("源は二つで、行動 ID は A1・A2")
        self.windows = tuple((int(k), int(a), int(b)) for k, a, b in windows)
        self.action_of = dict(action_of)
        self.cursor = 0                                  # まだ閉じていない最初の窓の位置
        self.pending: dict | None = None                 # 出す予定の意図（高々 1 つ）
        self.reports_pulse: PulseNumber | None = None
        self.reports: dict[UnitId, bool] = {}
        self.records: list[dict] = []                    # 層 A

    # -- 競合の口から呼ばれる ------------------------------------------------------
    def due(self, unit_id: UnitId, pulse: PulseNumber) -> str | None:
        """この Pulse に、この口が出す意図の行動 ID（なければ None）。"""
        p = self.pending
        if p is not None and p["unit"] == unit_id and p["pulse"] == pulse:
            return p["action"]
        return None

    def emitted(self, unit_id: UnitId, pulse: PulseNumber) -> None:
        p = self.pending
        if p is None or p["unit"] != unit_id or p["pulse"] != pulse:
            raise I2Error(f"Pulse {pulse}：{unit_id} に出す予定はない")
        self.records[p["record"]]["emitted"] = True
        self.pending = None

    def report(self, unit_id: UnitId, pulse: PulseNumber, fired: bool) -> None:
        if unit_id not in self.action_of:
            raise I2Error(f"源でない {unit_id} からの報告")
        if self.pending is not None and self.pending["pulse"] < pulse:
            raise I2Error(f"Pulse {self.pending['pulse']} に出す予定の意図が出ていない")
        if self.reports_pulse is None:
            self.reports_pulse = pulse
        elif self.reports_pulse != pulse:
            raise I2Error(f"Pulse {self.reports_pulse} の報告がそろわないまま Pulse {pulse} の報告が来た")
        if unit_id in self.reports:
            raise I2Error(f"Pulse {pulse}：{unit_id} の報告が二度来た")
        self.reports[unit_id] = bool(fired)
        if len(self.reports) == 2:
            fired_now = dict(self.reports)
            self.reports, self.reports_pulse = {}, None
            self._decide(pulse, fired_now)

    # -- 決定 ---------------------------------------------------------------------
    def _decide(self, t: PulseNumber, fired: Mapping[UnitId, bool]) -> None:
        if self.cursor >= len(self.windows):
            return
        k, a, b = self.windows[self.cursor]
        if t < a:
            return
        if t > b:
            raise I2Error(f"窓 {k} を Pulse {b} に閉じ損ねた")
        winners = sorted(u for u, f in fired.items() if f)
        if len(winners) == 2:
            self._close(k, a, b, TIE, t, None)
        elif len(winners) == 1:
            if self.pending is not None:
                raise I2Error("出す予定の意図が残ったまま、次の勝ちが決まった")
            self._close(k, a, b, self.action_of[winners[0]], t, winners[0])
        elif t == b:
            self._close(k, a, b, NONE, None, None)

    def _close(self, k, a, b, outcome, decision, winner) -> None:
        record = {"window": k, "open": a, "close": b, "outcome": outcome, "decision_pulse": decision,
                  "winner_unit": winner, "action": self.action_of[winner] if winner else None,
                  "emit_pulse": decision + 1 if winner else None, "emitted": False}
        self.records.append(record)
        if winner is not None:
            self.pending = {"unit": winner, "action": record["action"], "pulse": decision + 1,
                            "record": len(self.records) - 1}
        self.cursor += 1

    def export_state(self) -> dict[str, JsonValue]:
        return {"windows": [list(w) for w in self.windows], "action_of": dict(sorted(self.action_of.items())),
                "cursor": self.cursor, "pending": None if self.pending is None else dict(self.pending),
                "reports_pulse": self.reports_pulse, "reports": dict(sorted(self.reports.items())),
                "records": [dict(r) for r in self.records]}


class CompetitionTap:
    """源の Unit を包む競合の口（契約 §2.5）。

    1. 中の Unit の tick をそのまま呼ぶ（提案・発火を変えない：EC-6）
    2. 決定の部品が「この Pulse に、この口が出す」と示したら、意図の提案を出力路 `intent` に 1 つ足す（EC-5・EC-8）
    3. この Pulse に発火したかだけを報告する（EC-2・EC-3）
    """

    def __init__(self, inner: CognitiveUnit, decider: I2Decider, *, port: str = INTENT_PORT) -> None:
        self._inner = inner
        self.decider = decider
        self._port = port

    @property
    def unit_id(self) -> UnitId:
        return self._inner.unit_id

    def tick(self, view: ReceptiveView, context: PulseContext) -> UnitStepResult:
        step = self._inner.tick(view, context)
        action = self.decider.due(self.unit_id, context.pulse)
        if action is not None:
            intent = ProposedDelta(kind=DeltaKind.INTENT, payload=action, output_port=self._port)
            step = replace(step, proposed_deltas=tuple(step.proposed_deltas) + (intent,))
            self.decider.emitted(self.unit_id, context.pulse)
        self.decider.report(self.unit_id, context.pulse, step.activity is not None)
        return step

    def handle_kernel_result(self, task, result, context: PulseContext) -> UnitStepResult:
        return self._inner.handle_kernel_result(task, result, context)

    def export_state(self) -> JsonValue:
        return self._inner.export_state()

    def import_state(self, state: JsonValue) -> None:
        self._inner.import_state(state)


# ---- 世界（WB-1〜WB-9） ------------------------------------------------------------

CUE = "cue"
CONSEQUENCE = "consequence"
EXOGENOUS = "exogenous"


@dataclass(frozen=True)
class Reservation:
    rid: int
    kind: str                         # cue | consequence | exogenous
    receptor_id: ComponentId
    pulse: PulseNumber
    origin: str | None = None         # 結果なら、出どころの意図の Delta の ID


class AS2bWorld:
    """世界の規則と状態。予約の正本はここだけに置く（WB-1）。脳の部品への参照を持たない（WB-8）。

    規則（WB-3）：中身が c の意図が Pulse e に来たら、手がかりの Receptor に Pulse e ＋ L − 1 の刺激を 1 つ予約する。
    中身が c でない意図には何もしない。respond が偽なら意図を記録するだけ（WB-9）。多重度は 1 予約に 1 出来事（WB-5）。
    """

    def __init__(self, *, cue_receptor: ComponentId, delay: int, rule_c: str, cues: Iterable[PulseNumber] = (),
                 respond: bool = True, exogenous: Iterable[tuple[PulseNumber, ComponentId]] = ()) -> None:
        if delay < 2:
            raise ValueError(f"L = {delay}：今の Pulse の順序では L ≥ 2 でなければならない（命題 W-1）")
        if rule_c not in ACTION_IDS:
            raise ValueError(f"規則 c は {ACTION_IDS} のどれか（{rule_c}）")
        self.cue_receptor = cue_receptor
        self.delay = delay
        self.rule_c = rule_c
        self.respond = respond
        self.pending: list[Reservation] = []
        self.intents: list[tuple[PulseNumber, str, str, str]] = []     # 層 B：(Pulse, Delta の ID, 出どころ, 行動 ID)
        self.realized: list[tuple[PulseNumber, ComponentId, tuple[int, ...], int]] = []
        self.cancelled: list[Reservation] = []
        self.reserved: list[Reservation] = []          # これまでに置いた予約のすべて（記録。CT-W1 の照合に使う）
        self.last_drained: dict[ComponentId, PulseNumber] = {}
        self._next_rid = 0
        for pulse in sorted(cues):
            self.reserve(CUE, cue_receptor, pulse)
        for pulse, receptor_id in sorted(exogenous):
            self.reserve(EXOGENOUS, receptor_id, pulse)

    def reserve(self, kind: str, receptor_id: ComponentId, pulse: PulseNumber, origin: str | None = None) -> Reservation:
        if pulse <= self.last_drained.get(receptor_id, 0):
            raise AS1.PastPulseReservation(f"{receptor_id}：Pulse {pulse} はもう drain 済み")
        self._next_rid += 1
        reservation = Reservation(self._next_rid, kind, receptor_id, pulse, origin)
        self.pending.append(reservation)
        self.reserved.append(reservation)
        return reservation

    def receive_intent(self, pulse: PulseNumber, delta_id: str, source_id: str, action: str) -> None:
        self.intents.append((pulse, delta_id, source_id, action))
        if self.respond and action == self.rule_c:      # 規則が読むのは中身だけ（出どころを使わない：EC-9）
            self.reserve(CONSEQUENCE, self.cue_receptor, pulse + self.delay - 1, origin=delta_id)

    def cancel(self, rid: int) -> Reservation:
        for k, r in enumerate(self.pending):
            if r.rid == rid:
                del self.pending[k]
                self.cancelled.append(r)
                return r
        raise KeyError(f"予約 {rid} はない（成立済みか、取り消し済み）")

    def due(self, receptor_id: ComponentId, pulse: PulseNumber) -> list[Reservation]:
        return [r for r in self.pending if r.receptor_id == receptor_id and r.pulse == pulse]

    def drain(self, receptor_id: ComponentId, pulse: PulseNumber) -> int:
        if pulse <= self.last_drained.get(receptor_id, 0):
            raise ValueError(f"{receptor_id}：Pulse {pulse} は drain 済み（最後は {self.last_drained[receptor_id]}）")
        due = self.due(receptor_id, pulse)
        self.pending = [r for r in self.pending if r not in due]
        self.last_drained[receptor_id] = pulse
        if due:
            self.realized.append((pulse, receptor_id, tuple(r.rid for r in due), len(due)))
        return len(due)

    def export_state(self) -> dict[str, JsonValue]:
        def rows(rs: Sequence[Reservation]) -> list:
            return [[r.rid, r.kind, r.receptor_id, r.pulse, r.origin] for r in rs]
        return {
            "rule": {"cue_receptor": self.cue_receptor, "delay": self.delay, "rule_c": self.rule_c,
                     "respond": self.respond, "multiplicity": AS1.PER_RESERVATION},
            "pending": rows(self.pending),
            "cancelled": rows(self.cancelled),
            "reserved": rows(self.reserved),
            "intents": [list(x) for x in self.intents],
            "realized": [[p, r, list(rids), n] for p, r, rids, n in self.realized],
            "last_drained": dict(sorted(self.last_drained.items())),
            "next_rid": self._next_rid,
        }


class AS2bEffector:
    """受けた意図の Delta を世界に渡すだけ。選ばない・消さない・替えない（AI3・EC-9）。"""

    def __init__(self, effector_id: ComponentId, world: AS2bWorld) -> None:
        self._effector_id = effector_id
        self.world = world
        self.received: list[str] = []

    @property
    def effector_id(self) -> ComponentId:
        return self._effector_id

    async def execute(self, delta: StateDelta) -> None:
        self.received.append(delta.delta_id)
        self.world.receive_intent(delta.created_pulse, delta.delta_id, delta.source_id, delta.payload)


# ---- 組み立て ------------------------------------------------------------------------

@dataclass
class AS2bSystem:
    """個体（Application）と世界と出口と介入の部品を一つにまとめる。複製はこのまとまりごと行う（M1）。"""

    app: Application
    world: AS2bWorld
    decider: I2Decider | None
    connections: "AS1.InterventionConnections | None"
    roles: Roles
    seed: int
    schedule: TrialSchedule
    log: "AS1.AS1Log"
    meta: dict = field(default_factory=dict)

    @property
    def pulse(self) -> PulseNumber:
        return self.app.lifecycle.pulse

    def taps(self) -> list[CompetitionTap]:
        return [u for u in self.app.units.all() if isinstance(u, CompetitionTap)]

    def declare(self, interventions, label: str = "") -> None:
        self.connections.declare(interventions, label, boundary=self.pulse)

    def clear(self, label: str = "") -> None:
        self.connections.clear(label, boundary=self.pulse)

    def transplant(self, weights: Mapping[str, float]) -> None:
        AS1.transplant(self.app, weights, wrapper=self.connections)

    def switch_world(self, respond: bool, label: str = "") -> None:
        self.world.respond = bool(respond)
        self.meta.setdefault("world_switches", []).append((self.pulse, label, bool(respond)))


def _birth(seed: int, tag: str):
    return parse_birth_state({"individual_id": f"anima-{tag}-{seed}", "seed": seed})


def build(seed: int, *, schedule: TrialSchedule, delay: int = 2, rule_c: str = ACTION_IDS[0], respond: bool = True,
          outlet: bool = True, world_cues: bool = True, exogenous: Iterable[tuple[PulseNumber, ComponentId]] = (),
          interventions: bool = True, log: "AS1.AS1Log | None" = None, state_sample_interval: int = 0) -> AS2bSystem:
    """AS2b の個体と世界と出口を組み立てる。

    - outlet が偽なら、源を包まない（出口を外した個体：CT-G1a′）。世界の手がかりの予約はそのまま
    - world_cues が偽なら、世界に手がかりの予約を入れない（再生の系：手がかりは exogenous の再生の予定で来る）。
      出口の窓は、どちらでも同じ予定から作る（WB-2・CT-W4）
    - exogenous：行動に依らない刺激の予定 [(Pulse, Receptor)]（再生の予定など）
    """
    schedule.check(delay)
    roles = assign_roles(seed)
    exogenous = list(exogenous)
    if world_cues:
        doubled = sorted(set(exogenous) & {(c, roles.cue_receptor) for c in schedule.cues})
        if doubled:
            # 再生の予定（replay_schedule）は成立した手がかりを含む。それを入れるときは world_cues を偽にする
            raise ScheduleConflict(f"手がかりを二重に予約する（{doubled[:3]}…）。再生の系では world_cues=False にする")
    world = AS2bWorld(cue_receptor=roles.cue_receptor, delay=delay, rule_c=rule_c,
                      cues=schedule.cues if world_cues else (), respond=respond, exogenous=exogenous)
    manifest = parse_neuroarchitecture(AS1.as1_manifest_raw())
    env = parse_environment(AS1.environment_raw(with_effector=True))
    log = log if log is not None else AS1.AS1Log()

    decider = None
    unit_overrides: dict[str, CognitiveUnit] = {}
    if outlet:
        # 源の中身は、同じ設計図・同じ seed で組み立てた個体のものをそのまま使う（初期の状態とばらつきが同じ）
        scratch = build_application(manifest, env, _birth(seed, "as2b-scratch"),
                                    clock=FixedStepClock(PULSE_INTERVAL_SECONDS), event_log=AS1.AS1Log(keep=()))
        decider = I2Decider(schedule.windows, roles.action_of)
        for uid in (roles.source1, roles.source2):
            unit_overrides[uid] = CompetitionTap(scratch.units.get(uid), decider)

    holder: dict = {}

    def wrap(store):
        holder["c"] = AS1.InterventionConnections(store, manifest)
        return holder["c"]

    app = build_application(
        manifest, env, _birth(seed, "as2b"),
        clock=FixedStepClock(PULSE_INTERVAL_SECONDS),
        event_log=log,
        receptor_overrides={r: AS1.WorldReceptor(r, world) for r in RECEPTOR_OF.values()},
        effector_overrides={EFFECTOR_ID: AS2bEffector(EFFECTOR_ID, world)},
        unit_overrides=unit_overrides,
        run_metadata={"tool": "experiments/as2b_choice/as2b.py", "roles": roles.as_dict(), "delay": delay,
                      "rule_c": rule_c, "respond": respond, "outlet": outlet, "world_cues": world_cues,
                      "schedule": schedule.as_dict()},
        state_sample_interval=state_sample_interval,
        connection_wrapper=wrap if interventions else None,
    )
    meta = {"delay": delay, "rule_c": rule_c, "respond": respond, "outlet": outlet, "world_cues": world_cues}
    return AS2bSystem(app, world, decider, holder.get("c"), roles, seed, schedule, log, meta)


def build_c0(seed: int, exogenous: Iterable[tuple[PulseNumber, ComponentId]], log=None):
    """比べる C0 の個体（AS1 の道具と同じ）：C0 の設計図と、同じ外生の刺激の列。"""
    return AS1.build_c0(seed, exogenous, log)


def cue_events(system_or_roles, schedule: TrialSchedule) -> list[tuple[PulseNumber, ComponentId]]:
    roles = system_or_roles.roles if isinstance(system_or_roles, AS2bSystem) else system_or_roles
    return [(c, roles.cue_receptor) for c in schedule.cues]


advance_to = AS1.advance_to
sigma_diff = AS1.sigma_diff
replay_schedule = AS1.replay_schedule          # 世界の export_state の形が AS1 と同じ（realized・pending の行）


def clone(system: AS2bSystem) -> AS2bSystem:
    """M1：個体・世界・出口・介入の部品を一つの deepcopy で写す（二つの口の決定の部品の共有も保たれる）。

    来歴のログだけは新しい空のものに替える。
    """
    fresh = AS1.AS1Log(keep=system.log.keep)
    return copy.deepcopy(system, {id(system.log): fresh})


def sigma(system: AS2bSystem) -> dict:
    """比べる状態 Σ（契約 §4.1）：AS1 の Σ に、出口（決定の部品）の状態を足す。"""
    out = AS1.sigma(system.app, system.world)
    out["interventions"] = None if system.connections is None else system.connections.export_intervention_state()
    out["exit"] = None if system.decider is None else system.decider.export_state()
    return out


# ---- 層 A と層 B の外部の突合（CT-E10） --------------------------------------------

def audit(system: AS2bSystem) -> dict:
    """層 A（決定の部品の「出した」記録）と層 B（世界の受けた意図の記録）を、(Pulse, 出どころ, 行動 ID) で突き合わせる。

    走らせた後に、研究用の外部の部品として呼ぶ。結果は記録と解析にだけ使い、脳にも世界の規則にも戻さない。
    来歴のログに Delta の出来事があれば、それも層 B の写しとして突き合わせる。
    どの終了点でも「発行済みの意図の数（層 B）＋ 未発行の予定の数（層 A）＝ 勝ちの窓の数（層 A）」を確かめる。勝ちが
    最後の Pulse に決まり、翌 Pulse の発行の前に止まった窓は、持ち越しとして数え、失敗や沈黙に数えない（#176 の申し送り ②）。
    """
    records = system.decider.records if system.decider is not None else []
    layer_a = [(r["emit_pulse"], r["winner_unit"], r["action"]) for r in records if r["emitted"]]
    carried = [r["window"] for r in records if r["winner_unit"] is not None and not r["emitted"]]
    layer_b = [(p, src, act) for p, _did, src, act in system.world.intents]
    ids = [did for _p, did, _src, _act in system.world.intents]
    wins = sum(1 for r in records if r["winner_unit"] is not None)
    identity = len(layer_b) + len(carried) == wins          # 発行済み（層 B）＋ 未発行の予定（層 A）＝ 勝ちの窓（層 A）
    ca, cb = Counter(layer_a), Counter(layer_b)
    only_a, only_b = sorted((ca - cb).elements()), sorted((cb - ca).elements())
    log_b = None
    if RuntimeEventType.DELTA in system.log.keep:
        log_b = sorted((e.data["created_pulse"], e.data["source_id"], e.data["payload"], e.data["delta_id"])
                       for e in system.log.of(RuntimeEventType.DELTA) if e.data["kind"] == DeltaKind.INTENT)
    world_b = sorted((p, src, act, did) for p, did, src, act in system.world.intents)
    ok = (not only_a and not only_b and len(ids) == len(set(ids)) and len(set(layer_a)) == len(layer_a)
          and (log_b is None or log_b == world_b) and identity and len(carried) <= 1)
    return {"ok": ok, "matched": len(layer_a) - len(only_a), "only_in_layer_a": only_a, "only_in_layer_b": only_b,
            "win_windows": wins, "issued": len(layer_b), "identity_issued_plus_carried_equals_wins": identity,
            "duplicate_delta_ids": len(ids) - len(set(ids)), "carried_over_windows": carried,
            "log_matches_world": None if log_b is None else log_b == world_b}
