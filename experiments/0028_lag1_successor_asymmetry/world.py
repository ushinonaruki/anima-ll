"""実験 0028 の道具（確定した事前登録 v0.2 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

L3 の候補 C-a・C-b（README §0〜§3）：同じ seed（同じ出生時の状態）から、二つの設計（protocol の brains.C0・brains.V1）で、
同じ 21 の札の列の本体を走らせる（計 42。README §2.1、protocol の conditions）。

- 札の列：O（試行 k の 3 つの枠 t_k、t_k ＋ b_offset、t_k ＋ c_offset に A・B・C）、M（同じ枠に A・C・B）、W1〜W19（試行の中の
  並べ替え：i ごとに protocol の乱数の流れ conditions.within_trial_shuffles.rng を 1 本だけ使い、試行 k ＝ 0, 1, … の順に
  [A, B, C] を 1 回ずつ並べ替えて、試行 k の 3 つの枠に置く）。V1 の本体は、C0 の同じ名前の本体と同じ札の列（同じ乱数の流れから
  作った同じ列）
- 経験は Pulse 1〜experience_end。その後はどの本体にも外からの入力はない。試しの複製は作らない（protocol の conditions.probes:
  none）。各本体を body_end（主の区間の終わり）まで進める
- 記録（README §8、protocol の records）：各本体の設計・出生時の状態・札の列・1〜終わりの全発火・experience_end・
  早い区間の終わり（experience_end ＋ delay）・body_end の全状態を、実装の内部表現の値のまま（丸めずに）保存する。
  操作の確認（README §7）のために、ほかに次の全状態も残す（判定の量には使わない）：
  - 札が O と最初に違う Pulse の 1 つ前（札が分かれる前の一致の確認）
  - 最初の刺激の Pulse（trials.first）とその次の Pulse の終わり（最初の刺激の Receptor の駆動と、それに続く Unit の駆動が
    記録した全状態に現れるようにする：V1 の重みの一定・Receptor の駆動の重みの確認が、空の確認にならないため）

この道具は、ほかの実験の道具（world.py など）を読み込まない。脳の設計図のパスは protocol の brains.<設計>.manifest から読む。
観測の量（N・Δ・D・外にあるか・h・補助の量）はここでは計算しない（analyze.py が、操作の確認がすべて成り立ったときだけ計算する）。
"""

import asyncio
import random
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.bootstrap import Application, build_application
from anima_ll.domain.model.identifiers import ComponentId, PulseNumber
from anima_ll.domain.model.runtime_event import RuntimeEvent, RuntimeEventType
from anima_ll.domain.model.sensory_event import SensoryEvent

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE.relative_to(ROOT) / "protocol.yaml"
PROTOCOL = yaml.safe_load((ROOT / PROTOCOL_PATH).read_text(encoding="utf-8"))

# 実験の ID・乱数の流れの名前・並べ替えの数・設計は protocol から読む
EXPERIMENT = PROTOCOL["experiment"]
RNG_SHUFFLE = PROTOCOL["conditions"]["within_trial_shuffles"]["rng"]
K = PROTOCOL["conditions"]["within_trial_shuffles"]["count"]
DESIGNS = tuple(PROTOCOL["conditions"]["designs"])          # ("C0", "V1")
ROLES = ("A", "B", "C")
BODIES = ("O", "M") + tuple(f"W{i}" for i in range(1, K + 1))
SHUFFLES = BODIES[2:]
WINDOWS = ("main", "early")                                  # protocol の timeline.count_window_main（主）・count_window_early（補助）

# protocol の式・名前の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
DELAY_MULTIPLE = 5                                           # 0027 と同じ倍数（README §3.4。新しく選んだ値ではない）
DELAY = f"{DELAY_MULTIPLE} * adaptation_tau / pulse_interval_seconds"
COUNT_WINDOW_MAIN = {"first": "experience_end + delay + 1", "length": "trials.count * trials.every",
                     "last": "count_window_main.first + count_window_main.length - 1", "role": "primary"}
COUNT_WINDOW_EARLY = {"first": "experience_end + 1", "last": "experience_end + delay", "role": "auxiliary"}
BODY_RUNS_TO = "count_window_main.last"
SCHEDULES = {"O": "ordered", "M": "mirrored", "within_trial_shuffles": "shuffled_labels_within_each_trial"}
WITHIN_TRIAL_PROCEDURE = ("for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, shuffle the list "
                          "[A, B, C] once with that stream and assign it to (t_k, t_k + b_offset, t_k + c_offset)")
MIRROR = {"A": "A", "B": "C", "C": "B"}

UNIT_FIELDS = ("activity", "adaptation", "refractory_remaining", "fire_count")
CONNECTION_FIELDS = ("weight", "pre_trace", "post_trace")
FULL_STATE_FIELDS = ("pulse", "units", "connections", "drives", "deltas")   # protocol の records.full_state_fields


# ---- 時間の流れ（Plan）-------------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """経験・二つの数える区間・本体の終わり。本番・smoke は plan_from(protocol) だけを使う（run.py は Plan を受け取らない）。

    契約テストは同じ式で値だけを小さくした Plan（make_plan）を使う。analyze.py は、本番・smoke の生の記録の Plan が
    plan_from(protocol) と完全に同じことを確かめる。
    """
    trials: int
    experience_end: PulseNumber
    delay: int
    early: tuple[PulseNumber, PulseNumber]       # 補助の区間 [S, E]
    main: tuple[PulseNumber, PulseNumber]        # 主の区間 [S, E]
    body_end: PulseNumber
    first_stimulus: tuple[PulseNumber, PulseNumber]   # 最初の刺激の Pulse とその次（確認のための全状態）

    def window(self, w: str) -> tuple[PulseNumber, PulseNumber]:
        return {"main": self.main, "early": self.early}[w]

    @property
    def snapshots(self) -> tuple[PulseNumber, PulseNumber, PulseNumber]:
        """protocol の records の full_state_12000・13500・25500（＝ 経験の終わり、早い区間の終わり、本体の終わり）。"""
        return self.experience_end, self.early[1], self.body_end

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("early", "main", "first_stimulus"):
            d[k] = list(d[k])
        return d


def make_plan(protocol: dict, trials: int, delay: int) -> Plan:
    """protocol の式（experience_end・二つの区間・body_runs_to）を、与えた試行の数・遅れに当てはめる。
    主の区間の長さは protocol の式どおり trials × trials.every（経験の長さと同じ）。"""
    tl = protocol["timeline"]
    if (tl["experience_end"] != EXPERIENCE_END or tl["count_window_main"] != COUNT_WINDOW_MAIN
            or tl["count_window_early"] != COUNT_WINDOW_EARLY or tl["body_runs_to"] != BODY_RUNS_TO):
        raise ValueError("timeline の式が道具と違う")
    if trials < 1 or delay < 1:
        raise ValueError("試行の数・遅れは 1 以上")
    t = tl["trials"]
    end = t["first"] - 1 + trials * t["every"]
    early = (end + 1, end + delay)
    main = (end + delay + 1, end + delay + trials * t["every"])
    return Plan(trials=trials, experience_end=end, delay=delay, early=early, main=main, body_end=main[1],
                first_stimulus=(t["first"], t["first"] + 1))


def _tau_pulses(protocol: dict) -> int:
    exact = manifest_raw(protocol, "C0")["defaults"]["dynamics"]["adaptation_tau"] / protocol["timeline"]["pulse_interval_seconds"]
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"adaptation_tau ÷ pulse_interval_seconds が整数でない（{exact}）")
    return n


def plan_from(protocol: dict) -> Plan:
    """protocol の Plan（本番・smoke）：試行 200、経験の終わり 12000、早い区間 12001〜13500、主の区間 13501〜25500、終わり 25500。"""
    tl = protocol["timeline"]
    if tl["delay"] != DELAY:
        raise ValueError("delay の式が道具と違う")
    return make_plan(protocol, tl["trials"]["count"], DELAY_MULTIPLE * _tau_pulses(protocol))


def plan_of(d: Mapping) -> Plan:
    """生の記録に書いた Plan を読み戻す。"""
    return Plan(trials=d["trials"], experience_end=d["experience_end"], delay=d["delay"], early=tuple(d["early"]),
                main=tuple(d["main"]), body_end=d["body_end"], first_stimulus=tuple(d["first_stimulus"]))


# ---- 役の割り当てと刺激（README §2）----------------------------------------------------------------------

def role_receptors(protocol: dict, seed: int) -> dict[str, ComponentId]:
    order = protocol["stimulus"]["role_orders"][(seed - 1) % 6]
    return dict(zip(ROLES, order))


def role_units(protocol: dict, seed: int) -> dict[str, ComponentId]:
    to_unit = protocol["brains"]["common"]["receptors"]
    return {role: to_unit[r] for role, r in role_receptors(protocol, seed).items()}


def trial_starts(protocol: dict, plan: Plan) -> list[PulseNumber]:
    t = protocol["timeline"]["trials"]
    return [t["first"] + k * t["every"] for k in range(plan.trials)]


def trial_slots(protocol: dict, plan: Plan) -> list[tuple[PulseNumber, PulseNumber, PulseNumber]]:
    """試行ごとの 3 つの枠の時刻。"""
    s = protocol["stimulus"]
    return [(t, t + s["b_offset"], t + s["c_offset"]) for t in trial_starts(protocol, plan)]


def ordered_labels(protocol: dict, plan: Plan) -> list[tuple[PulseNumber, str]]:
    """O：A を 1 ＋ 60k、B をその b_offset 後、C をその c_offset 後。"""
    out = []
    for slots in trial_slots(protocol, plan):
        out += list(zip(slots, ROLES))
    return sorted(out)


def mirrored_labels(protocol: dict, plan: Plan) -> list[tuple[PulseNumber, str]]:
    """M：O と同じ時刻に、A を 1 ＋ 60k、C をその b_offset 後、B をその c_offset 後（O の B と C の入れ替え）。"""
    return [(t, MIRROR[x]) for t, x in ordered_labels(protocol, plan)]


def rng_name(seed: int, i: int) -> str:
    return RNG_SHUFFLE.format(i=i, seed=seed)


def within_trial_labels(protocol: dict, plan: Plan, seed: int, i: int) -> list[tuple[PulseNumber, str]]:
    """W_i：random.Random(rng_name(seed, i)) の流れを 1 本だけ使い、試行 k ＝ 0, 1, … の順に、リスト [A, B, C] をその流れで
    1 回ずつ shuffle して、試行 k の 3 つの枠（t_k、t_k ＋ b_offset、t_k ＋ c_offset）に置く（README §2.1、protocol の procedure）。"""
    rng = random.Random(rng_name(seed, i))
    out = []
    for slots in trial_slots(protocol, plan):
        roles = list(ROLES)
        rng.shuffle(roles)
        out += list(zip(slots, roles))
    return sorted(out)


def shuffle_index(body: str) -> int:
    if body not in SHUFFLES:
        raise ValueError(f"{body} は試行の中の並べ替えの本体ではない")
    return int(body[1:])


def labels_of(protocol: dict, plan: Plan, seed: int, body: str) -> list[tuple[PulseNumber, str]]:
    """本体の札の列。設計（C0・V1）に依らない（V1 の本体は C0 の同じ名前の本体と同じ列）。"""
    if body == "O":
        return ordered_labels(protocol, plan)
    if body == "M":
        return mirrored_labels(protocol, plan)
    return within_trial_labels(protocol, plan, seed, shuffle_index(body))


def first_label_divergence(a: list, b: list) -> PulseNumber | None:
    """2 つの札の列（同じ時刻の列）が最初に違う Pulse（同じなら None）。"""
    if [t for t, _ in a] != [t for t, _ in b]:
        raise ValueError("札の列の時刻が違う（同じ時刻の列の札だけを並べ替える設計）")
    for (t, x), (_, y) in zip(a, b):
        if x != y:
            return t
    return None


# ---- Receptor・来歴のログ・個体の組み立て -------------------------------------------------------------------

class ScheduledReceptor:
    """決めた Pulse の番号のときに、中身なしの感覚の出来事を成立させる Receptor（実験の道具）。"""

    def __init__(self, receptor_id: ComponentId, pulses: Iterable[PulseNumber]) -> None:
        self._receptor_id = receptor_id
        self._pulses = frozenset(pulses)

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self, pulse: PulseNumber) -> tuple[SensoryEvent, ...]:
        return (SensoryEvent(self._receptor_id, pulse, None),) if pulse in self._pulses else ()


class ExperimentLog:
    """来歴ログのうち、この実験が使う出来事（感覚・発火）だけを持つ（メモリを抑えるため）。"""

    KEEP = frozenset({RuntimeEventType.SENSORY, RuntimeEventType.ACTIVITY})

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def append(self, event: RuntimeEvent) -> None:
        if event.type in self.KEEP:
            self.events.append(event)

    def spikes(self) -> dict[str, list[int]]:
        """Unit → 発火した Pulse の列（Pulse の順）。"""
        out: dict[str, list[int]] = {}
        for e in self.events:
            if e.type == RuntimeEventType.ACTIVITY:
                out.setdefault(e.data["unit_id"], []).append(e.pulse)
        return out

    def sensory(self) -> list[list]:
        return [[e.pulse, e.data["receptor_id"]] for e in self.events if e.type == RuntimeEventType.SENSORY]


def manifest_raw(protocol: dict, design: str) -> dict:
    """設計（C0・V1）の設計図を YAML として読んだ値（protocol の brains.<設計>.manifest）。"""
    return yaml.safe_load((ROOT / protocol["brains"][design]["manifest"]).read_text(encoding="utf-8"))


def plasticity(protocol: dict):
    """C0 の可塑性の規則の値（V1 には可塑的な接続がない）。"""
    return parse_neuroarchitecture(manifest_raw(protocol, "C0")).plasticity


def initial_connections(protocol: dict, design: str) -> dict[str, list[float]]:
    """設計図の、可塑性の対象の接続の出生時の状態 {connection_id: [重み, 0, 0]}（V1 では空）。"""
    m = parse_neuroarchitecture(manifest_raw(protocol, design))
    return {connection_id(p.source_id, p.target_id): [p.weight, 0.0, 0.0] for p in m.projections if p.plastic}


def projection_weights(protocol: dict, design: str) -> dict[tuple[str, str], float]:
    """設計図の接続（送り手 → 受け手）と重み（V1 では一生この値で伝わる）。"""
    m = parse_neuroarchitecture(manifest_raw(protocol, design))
    return {(p.source_id, p.target_id): p.weight for p in m.projections}


def connection_id(source: ComponentId, target: ComponentId) -> str:
    return f"{source}.main->{target}"


def unit_of(cid: str) -> tuple[str, str]:
    """"s1.main->s2" → ("s1", "s2")。"""
    src, dst = cid.split("->")
    return src.split(".")[0], dst


def receptors_for(protocol: dict, labels: list[tuple[PulseNumber, str]], seed: int) -> dict[ComponentId, ScheduledReceptor]:
    roles = role_receptors(protocol, seed)
    schedule: dict[ComponentId, list[PulseNumber]] = {r: [] for r in protocol["brains"]["common"]["receptors"]}
    for t, x in labels:
        schedule[roles[x]].append(t)
    return {r: ScheduledReceptor(r, pulses) for r, pulses in schedule.items()}


def build(protocol: dict, design: str, labels: list[tuple[PulseNumber, str]], seed: int, body: str,
          log: ExperimentLog) -> Application:
    """同じ seed の 42 の本体は、同じ出生時の状態（parse_birth_state の seed と個体の名前）から作る。
    違うのは設計図（C0・V1）と Receptor の予定だけ。"""
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brains"]["common"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol, design)),
        env,
        parse_birth_state({"individual_id": f"anima-{EXPERIMENT}-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=receptors_for(protocol, labels, seed),
        run_metadata={"experiment": EXPERIMENT, "design": design, "body": body,
                      "receptors": f"ScheduledReceptor（experiments/{HERE.name}/world.py）"},
    )


def advance_to(app: Application, pulse: PulseNumber) -> None:
    """個体を、Pulse `pulse` の処理が終わったところまで進める（すでにそこなら何もしない）。"""
    if app.lifecycle.pulse > pulse:
        raise ValueError(f"Pulse {app.lifecycle.pulse} からは {pulse} へ戻れない")
    if app.lifecycle.pulse < pulse:
        asyncio.run(app.lifecycle.run(max_pulses=pulse))


def full_state(app: Application) -> dict:
    """全状態（README §8）。値は実装が書き出したもののまま（丸めない）。欄は FULL_STATE_FIELDS の 5 つ。

    units：Unit → [activity, adaptation, refractory_remaining, fire_count]（UNIT_FIELDS の順）
    connections：Runtime が書き出した可塑的な接続 → [weight, pre_trace, post_trace]（CONNECTION_FIELDS の順）。
      V1 には可塑的な接続がないので空の辞書になるはず（欄は省かない。空であることは analyze.py が確かめる。
      この道具は Runtime が書き出したものをそのまま記録し、空にそろえない）
    drives：次の Pulse に届く駆動 [[送り手, 受け手, 重み, 成立の Pulse]]（並べ替えた列）。deltas：残っている Delta の数
    """
    units = {}
    for u in app.units.all():
        s = u.export_state()
        units[u.unit_id] = [s[f] for f in UNIT_FIELDS]
    conns = {cid: [v[f] for f in CONNECTION_FIELDS] for cid, v in app.connections.export_state().items()}
    bs = app.pulse_runtime.brain_state
    drives = sorted([d.source_id, d.target_id, d.weight, d.created_pulse] for d in bs.drives)
    return {"pulse": app.lifecycle.pulse, "units": units, "connections": conns, "drives": drives, "deltas": len(bs.deltas)}


def unit_dynamics(app: Application) -> dict:
    """Unit の力学の値（出生時の状態で決まり、変わらない）。"""
    return {u.unit_id: u.export_state()["dynamics"] for u in app.units.all()}


# ---- 1 つの本体（README §2・§8）--------------------------------------------------------------------------

def run_body(protocol: dict, plan: Plan, seed: int, design: str, body: str, labels: list,
             before_divergence: Iterable[int]) -> dict:
    """1 つの本体を出生から plan.body_end まで進める（試しの複製は作らない）。

    before_divergence：経験の途中で全状態を残す Pulse（札が O と最初に違う Pulse の 1 つ前。§7 の確認のため）。
    最初の刺激の Pulse とその次（plan.first_stimulus）の全状態も残す。
    """
    log = ExperimentLog()
    app = build(protocol, design, labels, seed, body, log)
    rec = {"body": body, "design": design, "birth": full_state(app), "dynamics": unit_dynamics(app)}
    want_div = {t for t in before_divergence if 0 < t < plan.experience_end}
    want_first = set(plan.first_stimulus)
    snaps: dict[int, dict] = {}
    for t in sorted(want_div | want_first):
        advance_to(app, t)
        snaps[t] = full_state(app)
    rec["first_stimulus"] = {str(t): snaps[t] for t in plan.first_stimulus}
    rec["before_divergence"] = {str(t): snaps[t] for t in sorted(want_div)}
    states = {}
    for t in plan.snapshots:
        advance_to(app, t)
        states[str(t)] = full_state(app)
    rec["states"] = states
    if app.lifecycle.pulse != plan.body_end:
        raise ValueError(f"本体が {plan.body_end} で終わっていない（{app.lifecycle.pulse}）")
    rec |= {"sensory": log.sensory(), "spikes": log.spikes()}
    return rec


# ---- 1 個体の測定（run.py と契約テストが同じ関数を使う）------------------------------------------------------

def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    """同じ seed から、二つの設計で 21 ずつ、42 の本体を測る。生の記録だけを返す（観測の量は計算しない）。"""
    plan = plan if plan is not None else plan_from(protocol)
    labels = {b: labels_of(protocol, plan, seed, b) for b in BODIES}
    diverge = {b: first_label_divergence(labels["O"], labels[b]) for b in BODIES if b != "O"}
    before = {d - 1 for d in diverge.values() if d is not None}
    designs = {}
    for design in DESIGNS:
        bodies = {}
        for b in BODIES:
            snap = before if b == "O" else ({diverge[b] - 1} if diverge[b] is not None else set())
            bodies[b] = run_body(protocol, plan, seed, design, b, labels[b], snap) | {
                "labels": [list(x) for x in labels[b]], "rng": rng_name(seed, shuffle_index(b)) if b in SHUFFLES else None,
                "first_divergence_from_O": diverge.get(b)}
        designs[design] = bodies
    return {"seed": seed, "plan": plan.as_dict(),
            "roles": {"receptors": role_receptors(protocol, seed), "units": role_units(protocol, seed)},
            "designs": designs}
