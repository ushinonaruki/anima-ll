"""AS1（自発の 1 つの行動）の最小の研究用の道具（docs/as1-minimal-implementation-contract.md の ②）。

【位置づけ】正式な実験ではない。事前登録（③）の前の、契約（①）を満たす道具と、その契約テストのためのもの。
Unit の力学・可塑性の規則・確定したパラメータは変えない。設計図は 0012（0028〜0033 と同じ C0）の値をそのまま読み、
Effector 1 つと、出力路 `intent` から Effector への投射だけを足す。

部品
- IntentSourceUnit：源の Unit を包み、その Unit が発火した Pulse に、意図 X の提案を出力路 `intent` で 1 つ足す（I1。IC-1〜IC-6）
- AS1World：世界の状態（予約の正本・受けた意図・成立した出来事）を持つ。意図が来たら t + L − 1 に結果を予約する（WC-1〜WC-6）
- WorldEffector・WorldReceptor：世界への入口と、世界に問い合わせるだけの Receptor（予定を持たない。WC-1b）
- InterventionConnections：接続の状態の口を包み、FB-1（伝達に渡す重みを 0）・FREEZE（重みの更新を止める）を行う（§5）
- clone・sigma：個体と世界の丸ごとの複製（M1）と、比べる状態 Σ の書き出し（§4）
"""

import asyncio
import copy
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType

import yaml

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.bootstrap import Application, build_application
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta, StateDelta
from anima_ll.domain.model.identifiers import ComponentId, JsonValue, PulseNumber, UnitId
from anima_ll.domain.model.manifest import NeuroarchitectureManifest
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.runtime_event import RuntimeEvent, RuntimeEventType
from anima_ll.domain.model.sensory_event import SensoryEvent
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_ll.domain.port.cognitive_unit import CognitiveUnit
from anima_ll.domain.port.connection_state import ConnectionKey, ConnectionStatePort
from anima_ll.neuroarchitecture.connections import ConnectionStore

ROOT = Path(__file__).resolve().parents[2]
C0_MANIFEST = ROOT / "experiments" / "0012_passive_world" / "neuroarchitecture.yaml"

INTENT_PORT = "intent"
ACTION_ID = "X"                       # 意味の名前を付けない（AI7・IC-6）
EFFECTOR_ID = "effector.y1"
UNITS = ("s1", "s2", "s3")
RECEPTOR_OF = {"s1": "receptor.x1", "s2": "receptor.x2", "s3": "receptor.x3"}   # C0 の 1 対 1（設計図のとおり）
PULSE_INTERVAL_SECONDS = 1.0          # 0012〜0033 と同じ


# ---- 設計図 ------------------------------------------------------------------------

def c0_manifest_raw() -> dict:
    return yaml.safe_load(C0_MANIFEST.read_text(encoding="utf-8"))


def as1_manifest_raw() -> dict:
    """C0 の設計図に、Effector 1 つと `sK.intent → effector` の投射だけを足す（力学・可塑性の値は C0 のまま）。

    どの Unit が源になるかは個体ごとの割り当て（K2）なので、3 つの Unit すべてに intent の投射を張る。
    源でない Unit は intent の出力路に何も出さないので、その投射は使われない。
    """
    raw = c0_manifest_raw()
    raw["interfaces"]["effectors"] = [EFFECTOR_ID]
    raw["projections"] = list(raw["projections"]) + [
        {"from": f"{u}.{INTENT_PORT}", "to": EFFECTOR_ID} for u in UNITS
    ]
    return raw


def environment_raw(*, with_effector: bool) -> dict:
    raw: dict = {
        "receptors": {r: {"kind": "scripted", "script": {}} for r in RECEPTOR_OF.values()},
        "runtime": {"pulse_interval_seconds": PULSE_INTERVAL_SECONDS},
    }
    if with_effector:
        raw["effectors"] = {EFFECTOR_ID: {"kind": "recording"}}
    return raw


# ---- 役の割り当て（K2・WC-4） ------------------------------------------------------

@dataclass(frozen=True)
class Roles:
    source: UnitId           # 源（行動の源）
    receiver: UnitId         # 受（結果を受ける Unit）
    other: UnitId            # 他

    @property
    def consequence_receptor(self) -> ComponentId:
        return RECEPTOR_OF[self.receiver]

    @property
    def source_receptor(self) -> ComponentId:
        return RECEPTOR_OF[self.source]

    def as_dict(self) -> dict[str, str]:
        return {"source": self.source, "receiver": self.receiver, "other": self.other,
                "consequence_receptor": self.consequence_receptor, "source_receptor": self.source_receptor}


def assign_roles(seed: int) -> Roles:
    """個体ごとに、名前で分けた乱数の流れ（Birth State の乱数とは別）で 3 つの役を割り当てる。"""
    order = list(UNITS)
    random.Random(f"as1-roles-{seed}").shuffle(order)
    return Roles(*order)


# ---- 出口：意図の源の Unit（I1） -----------------------------------------------------

class IntentSourceUnit:
    """源の Unit を包む。中の Unit の力学・出力（relay）はそのまま使い、発火した Pulse に意図の提案を 1 つ足す。

    - IC-1：発火 1 回につき意図 1 つ。発火したかどうか以外の条件（活動の値・時刻・過去の結果）を読まない
    - IC-2：中の Unit の提案（relay の分）を変えない・消さない
    - IC-3：意図は出力路 `intent` に出す（`main` ではない）。どこへ届くかは設計図の投射が決める
    - IC-4：状態を持たない。中の Unit の状態に触れない
    """

    def __init__(self, inner: CognitiveUnit, *, action_id: str = ACTION_ID, port: str = INTENT_PORT) -> None:
        self._inner = inner
        self._action_id = action_id
        self._port = port

    @property
    def unit_id(self) -> UnitId:
        return self._inner.unit_id

    def tick(self, view: ReceptiveView, context: PulseContext) -> UnitStepResult:
        step = self._inner.tick(view, context)
        if step.activity is None:
            return step
        intent = ProposedDelta(kind=DeltaKind.INTENT, payload=self._action_id, output_port=self._port)
        return replace(step, proposed_deltas=tuple(step.proposed_deltas) + (intent,))

    def handle_kernel_result(self, task, result, context: PulseContext) -> UnitStepResult:
        return self._inner.handle_kernel_result(task, result, context)

    def export_state(self) -> JsonValue:
        return self._inner.export_state()

    def import_state(self, state: JsonValue) -> None:
        self._inner.import_state(state)


# ---- 世界（WC-1〜WC-6） ------------------------------------------------------------

CONSEQUENCE = "consequence"
EXOGENOUS = "exogenous"
PER_RESERVATION = "per_reservation"   # 予約 1 つに感覚の出来事 1 つ（AS1 の第一候補。WC-1c）
MERGE = "merge"                       # 同じ Receptor・同じ Pulse の予約をまとめて出来事 1 つ


@dataclass(frozen=True)
class Reservation:
    rid: int
    kind: str                         # consequence | exogenous
    receptor_id: ComponentId
    pulse: PulseNumber
    origin: str | None = None         # 結果なら、出どころの意図の Delta の ID


class PastPulseReservation(ValueError):
    """もう drain した Pulse への予約（W-1：今の Pulse の順序では L ≥ 2）。"""


class AS1World:
    """世界の規則と状態。予約の正本はここだけに置く（WC-1b）。脳の部品への参照を持たない（WC-3）。

    規則（WC-2）：意図 X が Pulse t に来たら、結果の Receptor に Pulse t + L − 1 の刺激を 1 つ予約する。
    結果の中身は空。respond が偽なら意図を記録するだけで何も予約しない（開いたループ・C0 への還元：WC-6）。
    """

    def __init__(self, *, consequence_receptor: ComponentId, delay: int, multiplicity: str = PER_RESERVATION,
                 respond: bool = True, exogenous: Iterable[tuple[PulseNumber, ComponentId]] = ()) -> None:
        if delay < 2:
            raise ValueError(f"L = {delay}：今の Pulse の順序では L ≥ 2 でなければならない（命題 W-1）")
        if multiplicity not in (PER_RESERVATION, MERGE):
            raise ValueError(f"未知の多重度の規則: {multiplicity}")
        self.consequence_receptor = consequence_receptor
        self.delay = delay
        self.multiplicity = multiplicity
        self.respond = respond
        self.pending: list[Reservation] = []
        self.intents: list[tuple[PulseNumber, str]] = []          # (Pulse, 意図の Delta の ID)
        self.realized: list[tuple[PulseNumber, ComponentId, tuple[int, ...], int]] = []   # (Pulse, Receptor, 予約, 出来事の数)
        self.cancelled: list[Reservation] = []
        self.last_drained: dict[ComponentId, PulseNumber] = {}
        self._next_rid = 0
        for pulse, receptor_id in sorted(exogenous):
            self.reserve(EXOGENOUS, receptor_id, pulse)

    def reserve(self, kind: str, receptor_id: ComponentId, pulse: PulseNumber, origin: str | None = None) -> Reservation:
        if pulse <= self.last_drained.get(receptor_id, 0):
            raise PastPulseReservation(f"{receptor_id}：Pulse {pulse} はもう drain 済み")
        self._next_rid += 1
        reservation = Reservation(self._next_rid, kind, receptor_id, pulse, origin)
        self.pending.append(reservation)
        return reservation

    def receive_intent(self, pulse: PulseNumber, delta_id: str) -> None:
        self.intents.append((pulse, delta_id))
        if self.respond:
            self.reserve(CONSEQUENCE, self.consequence_receptor, pulse + self.delay - 1, origin=delta_id)

    def cancel(self, rid: int) -> Reservation:
        """識別子で、まだ成立していない予約を 1 つだけ取り消す（WC-1c・CT-Σ5）。"""
        for k, r in enumerate(self.pending):
            if r.rid == rid:
                del self.pending[k]
                self.cancelled.append(r)
                return r
        raise KeyError(f"予約 {rid} はない（成立済みか、取り消し済み）")

    def due(self, receptor_id: ComponentId, pulse: PulseNumber) -> list[Reservation]:
        return [r for r in self.pending if r.receptor_id == receptor_id and r.pulse == pulse]

    def drain(self, receptor_id: ComponentId, pulse: PulseNumber) -> int:
        """その Pulse にその Receptor で成立する出来事の数を返し、予約を成立済みに移す。"""
        due = self.due(receptor_id, pulse)
        self.pending = [r for r in self.pending if r not in due]
        self.last_drained[receptor_id] = pulse
        count = len(due) if self.multiplicity == PER_RESERVATION else (1 if due else 0)
        if due:
            self.realized.append((pulse, receptor_id, tuple(r.rid for r in due), count))
        return count

    def export_state(self) -> dict[str, JsonValue]:
        def rows(rs: Sequence[Reservation]) -> list:
            return [[r.rid, r.kind, r.receptor_id, r.pulse, r.origin] for r in rs]
        return {
            "rule": {"consequence_receptor": self.consequence_receptor, "delay": self.delay,
                     "multiplicity": self.multiplicity, "respond": self.respond},
            "pending": rows(self.pending),
            "cancelled": rows(self.cancelled),
            "intents": [list(x) for x in self.intents],
            "realized": [[p, r, list(rids), n] for p, r, rids, n in self.realized],
            "last_drained": dict(sorted(self.last_drained.items())),
            "next_rid": self._next_rid,
        }


class WorldEffector:
    """受けた意図の Delta を世界に渡すだけ。選ばない・消さない（AI3・IC-5）。"""

    def __init__(self, effector_id: ComponentId, world: AS1World) -> None:
        self._effector_id = effector_id
        self.world = world
        self.received: list[str] = []

    @property
    def effector_id(self) -> ComponentId:
        return self._effector_id

    async def execute(self, delta: StateDelta) -> None:
        self.received.append(delta.delta_id)
        self.world.receive_intent(delta.created_pulse, delta.delta_id)


class WorldReceptor:
    """自分の予定を持たず、drain のときに世界に問い合わせて、成立した出来事を返す（WC-1b）。"""

    def __init__(self, receptor_id: ComponentId, world: AS1World) -> None:
        self._receptor_id = receptor_id
        self.world = world

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self, pulse: PulseNumber) -> tuple[SensoryEvent, ...]:
        n = self.world.drain(self._receptor_id, pulse)
        return tuple(SensoryEvent(self._receptor_id, pulse, None) for _ in range(n))


# ---- 介入（§5） ---------------------------------------------------------------------

FB1 = "FB1"          # 伝達に渡す重みを 0 にする（中の重みは規則どおり動く）
FREEZE = "FREEZE"    # 重みの更新を止める（CF-2・FB-2・PC-1・PC-2 は対象と区間の違い）
ADVANCE = "advance"  # FREEZE の第一候補：重みは据え置き、痕跡は規則どおり進める
HOLD = "hold"        # 痕跡も据え置く


@dataclass(frozen=True)
class Intervention:
    kind: str
    targets: frozenset[str]           # 接続の ID（"s1.main->s2" の形）
    trace_policy: str = ADVANCE


class InterventionConnections:
    """接続の状態の口（ConnectionStatePort）を包む研究用の部品。中の ConnectionStore が重みの値を持つ。

    - 介入を宣言していなければ、中の ConnectionStore の操作をそのまま渡す（CT-I1）
    - FB-1：weights() が伝達に返す写しの、対象の接続の値だけを 0 にする。中の重みは触らない（CT-I2）
    - FREEZE：apply_activity の後に、対象の接続の重みを、宣言した時点の値に公開の import_state で戻す（CT-I3）
    介入の始まりと終わりは、Pulse のあいだに declare / clear で切り替える（区間は呼んだ側が記録する）。
    """

    def __init__(self, inner: ConnectionStore, manifest: NeuroarchitectureManifest) -> None:
        self.inner = inner
        self._key_of = {p.connection_id: (p.source_id, p.source_port, p.target_id) for p in manifest.projections}
        self._plastic = {p.connection_id for p in manifest.projections if p.plastic}
        self.active: tuple[Intervention, ...] = ()
        self._frozen: dict[str, dict[str, float]] = {}
        self.history: list[tuple[str, tuple[Intervention, ...]]] = []
        self.last_returned: Mapping[ConnectionKey, float] | None = None
        self.last_inner: Mapping[ConnectionKey, float] | None = None

    def declare(self, interventions: Sequence[Intervention], label: str = "") -> None:
        for iv in interventions:
            if iv.kind not in (FB1, FREEZE):
                raise ValueError(f"未知の介入: {iv.kind}")
            unknown = set(iv.targets) - set(self._key_of)
            if unknown:
                raise KeyError(f"未知の接続: {sorted(unknown)}")
            if iv.kind == FREEZE and not set(iv.targets) <= self._plastic:
                raise ValueError("FREEZE の対象は可塑的な接続だけ")
            if iv.trace_policy not in (ADVANCE, HOLD):
                raise ValueError(f"未知の痕跡の扱い: {iv.trace_policy}")
        state = self.inner.export_state()
        self._frozen = {}
        for iv in interventions:
            if iv.kind == FREEZE:
                for cid in iv.targets:
                    self._frozen[cid] = {**state[cid], "policy": iv.trace_policy}
        self.active = tuple(interventions)
        self.history.append((label, self.active))

    def clear(self, label: str = "") -> None:
        self.declare((), label)

    def masked_keys(self) -> set[ConnectionKey]:
        return {self._key_of[cid] for iv in self.active if iv.kind == FB1 for cid in iv.targets}

    def weights(self) -> Mapping[ConnectionKey, float]:
        inner = self.inner.weights()
        masked = self.masked_keys()
        if masked:
            returned = dict(inner)
            for key in masked:
                returned[key] = 0.0
            returned = MappingProxyType(returned)
        else:
            returned = inner
        # 契約テスト（CT-I2）のための写し。複製（deepcopy）できるように普通の dict で持つ
        self.last_inner, self.last_returned = dict(inner), dict(returned)
        return returned

    def apply_activity(self, fired, delta_time: float) -> None:
        self.inner.apply_activity(fired, delta_time)
        if not self._frozen:
            return
        now = self.inner.export_state()
        patch = {}
        for cid, frozen in self._frozen.items():
            traces = now[cid] if frozen["policy"] == ADVANCE else frozen
            patch[cid] = {"weight": frozen["weight"], "pre_trace": traces["pre_trace"],
                          "post_trace": traces["post_trace"]}
        self.inner.import_state(patch)

    def export_state(self) -> dict[str, JsonValue]:
        return self.inner.export_state()


def transplant(app: Application, weights: Mapping[str, float]) -> None:
    """TRANSPLANT（PC-4）：宣言した接続の重みだけを置き換える。痕跡とほかの Σ は変えない（CT-I4）。Pulse のあいだに呼ぶ。"""
    state = app.connections.export_state()
    app.connections.import_state({cid: {"weight": float(w), "pre_trace": state[cid]["pre_trace"],
                                        "post_trace": state[cid]["post_trace"]} for cid, w in weights.items()})


def pair_sums(connections_state: Mapping[str, Mapping[str, float]]) -> dict[tuple[str, str], float]:
    """可塑的な組ごとの重みの和（F1 の記録：CT-I5）。"""
    sums: dict[tuple[str, str], float] = {}
    for cid, v in connections_state.items():
        src, tgt = cid.split(".", 1)[0], cid.split("->")[1]
        pair = tuple(sorted((src, tgt)))
        sums[pair] = sums.get(pair, 0.0) + float(v["weight"])
    return dict(sorted(sums.items()))


# ---- 個体と世界の組み立て -------------------------------------------------------------

class AS1Log:
    """来歴のログのうち、道具と契約テストが使う出来事だけを持つ。"""

    DEFAULT_KEEP = frozenset({RuntimeEventType.RUN, RuntimeEventType.SENSORY, RuntimeEventType.ACTIVITY,
                              RuntimeEventType.DELTA, RuntimeEventType.EFFECT})

    def __init__(self, keep: Iterable[str] | None = None) -> None:
        self.keep = frozenset(keep) if keep is not None else self.DEFAULT_KEEP
        self.events: list[RuntimeEvent] = []

    def append(self, event: RuntimeEvent) -> None:
        if event.type in self.keep:
            self.events.append(event)

    def of(self, event_type: str) -> list[RuntimeEvent]:
        return [e for e in self.events if e.type == event_type]

    def activity(self) -> list[tuple[PulseNumber, str]]:
        return [(e.pulse, e.data["unit_id"]) for e in self.of(RuntimeEventType.ACTIVITY)]

    def sensory(self) -> list[tuple[PulseNumber, str]]:
        return [(e.pulse, e.data["receptor_id"]) for e in self.of(RuntimeEventType.SENSORY)]


@dataclass
class AS1System:
    """個体（Application）と世界と介入の部品を一つにまとめる。複製はこのまとまりごと行う（M1）。"""

    app: Application
    world: AS1World
    connections: InterventionConnections | None
    roles: Roles
    seed: int
    log: AS1Log
    meta: dict = field(default_factory=dict)

    @property
    def pulse(self) -> PulseNumber:
        return self.app.lifecycle.pulse


def _birth(seed: int, tag: str):
    return parse_birth_state({"individual_id": f"anima-{tag}-{seed}", "seed": seed})


def build(seed: int, *, delay: int = 2, multiplicity: str = PER_RESERVATION, respond: bool = True,
          exogenous: Iterable[tuple[PulseNumber, ComponentId]] = (), outlet: bool = True,
          interventions: bool = True, log: AS1Log | None = None, state_sample_interval: int = 0) -> AS1System:
    """AS1 の個体と世界を組み立てる。

    - outlet が偽なら、源を包まない（出口を外した個体：WC-6・CT-G1a）
    - interventions が偽なら、接続の状態の口を包まない（CT-I1 の比べる相手）
    - exogenous：行動に依らない刺激の予定 [(Pulse, Receptor)]（C0 への還元の参照の入力など）
    """
    roles = assign_roles(seed)
    world = AS1World(consequence_receptor=roles.consequence_receptor, delay=delay, multiplicity=multiplicity,
                     respond=respond, exogenous=exogenous)
    manifest = parse_neuroarchitecture(as1_manifest_raw())
    env = parse_environment(environment_raw(with_effector=True))
    log = log if log is not None else AS1Log()

    unit_overrides = {}
    if outlet:
        # 源の Unit の中身は、同じ設計図・同じ seed で組み立てた個体のものをそのまま使う（初期の状態とばらつきが同じ）
        scratch = build_application(manifest, env, _birth(seed, "as1-scratch"), clock=FixedStepClock(PULSE_INTERVAL_SECONDS),
                                    event_log=AS1Log(keep=()))
        unit_overrides = {roles.source: IntentSourceUnit(scratch.units.get(roles.source))}

    holder: dict[str, InterventionConnections] = {}

    def wrap(store):
        holder["c"] = InterventionConnections(store, manifest)
        return holder["c"]

    app = build_application(
        manifest, env, _birth(seed, "as1"),
        clock=FixedStepClock(PULSE_INTERVAL_SECONDS),
        event_log=log,
        receptor_overrides={r: WorldReceptor(r, world) for r in RECEPTOR_OF.values()},
        effector_overrides={EFFECTOR_ID: WorldEffector(EFFECTOR_ID, world)},
        unit_overrides=unit_overrides,
        run_metadata={"tool": "experiments/as1_closed_loop/as1.py", "roles": roles.as_dict(),
                      "delay": delay, "multiplicity": multiplicity, "respond": respond, "outlet": outlet},
        state_sample_interval=state_sample_interval,
        connection_wrapper=wrap if interventions else None,
    )
    return AS1System(app, world, holder.get("c"), roles, seed, log,
                     {"delay": delay, "multiplicity": multiplicity, "respond": respond, "outlet": outlet})


def build_c0(seed: int, exogenous: Iterable[tuple[PulseNumber, ComponentId]], log: AS1Log | None = None) -> tuple[Application, AS1World]:
    """比べる C0 の個体：C0 の設計図（出口・Effector なし）と、同じ外生の刺激の列（世界の部品で与える）。"""
    world = AS1World(consequence_receptor=RECEPTOR_OF["s1"], delay=2, respond=False, exogenous=exogenous)
    env = parse_environment(environment_raw(with_effector=False))
    app = build_application(
        parse_neuroarchitecture(c0_manifest_raw()), env, _birth(seed, "as1-c0"),
        clock=FixedStepClock(PULSE_INTERVAL_SECONDS), event_log=log if log is not None else AS1Log(),
        receptor_overrides={r: WorldReceptor(r, world) for r in RECEPTOR_OF.values()},
    )
    return app, world


def advance_to(app: Application, pulse: PulseNumber) -> None:
    """Pulse `pulse` の処理が終わったところ（Pulse のあいだ）まで進める。"""
    if app.lifecycle.pulse > pulse:
        raise ValueError(f"Pulse {app.lifecycle.pulse} からは {pulse} へ戻れない")
    if app.lifecycle.pulse < pulse:
        asyncio.run(app.lifecycle.run(max_pulses=pulse))


def clone(system: AS1System) -> AS1System:
    """M1：個体・世界・介入の部品を一つの deepcopy で写す。来歴のログだけは新しい空のものに替える。"""
    fresh = AS1Log(keep=system.log.keep)
    return copy.deepcopy(system, {id(system.log): fresh})


# ---- 比べる状態 Σ（§4.1） ------------------------------------------------------------

def sigma(system_or_app, world: AS1World | None = None) -> dict:
    """分岐の時点で二つの系がそろえるべき状態の書き出し（比べるための写し）。

    Runtime の内部の状態は、研究用の道具が読むだけ（書き換えない）。
    """
    if isinstance(system_or_app, AS1System):
        app, world = system_or_app.app, system_or_app.world
        wrapper = system_or_app.connections
    else:
        app, wrapper = system_or_app, None
    rt = app.pulse_runtime
    state = rt.brain_state
    return {
        "pulse": app.lifecycle.pulse,
        "clock": app.lifecycle._clock.now(),
        "units": {u.unit_id: u.export_state() for u in app.units.all()},
        "connections": app.connections.export_state(),
        "drives": [(d.source_id, d.target_id, d.weight, d.created_pulse) for d in state.drives],
        "deltas": [(d.delta_id, d.source_id, d.target_id, d.kind, d.expires_after_pulse) for d in state.deltas],
        "issuer": dict(sorted(rt._issuer._counters.items())),
        "runtime": {"intent_seq": rt._intent_seq, "degraded": rt._degraded,
                    "in_flight": len(rt._coordinator.in_flight())},
        "world": world.export_state() if world is not None else None,
        "interventions": None if wrapper is None else [(iv.kind, sorted(iv.targets), iv.trace_policy) for iv in wrapper.active],
    }


def intent_pulses(system: AS1System) -> list[PulseNumber]:
    return [p for p, _ in system.world.intents]


def first_intent_after(system: AS1System, pulse: PulseNumber) -> PulseNumber | None:
    later = [p for p in intent_pulses(system) if p > pulse]
    return min(later) if later else None
