"""実験 0025 の道具（確定した事前登録 v0.1 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

試行の中の並べ替えの参照 E2（README §1・§2）：設計図・時間の流れ・試し・記録は 0023 と同じ（C0、可塑性あり）。
違うのは主の参照分布の作り方（W1〜W19）・乱数の流れの名前・seed だけ。

- 21 の本体（README §2、protocol の conditions）：同じ seed（同じ出生時の状態）から、O（順序あり）、M（鏡。補助）、
  W1〜W19（試行の中の並べ替え：i ごとに protocol の乱数の流れ conditions.within_trial_shuffles.rng を 1 本だけ使い、
  試行 k ＝ 0, 1, … の順に [A, B, C] を 1 回ずつ並べ替えて、試行 k の 3 つの枠（t_k、t_k ＋ b_offset、t_k ＋ c_offset）に置く）。
  どの条件でも、どの試行でも A・B・C が 1 回ずつ来る。経験は Pulse 1〜experience_end。その後はどの本体にも外からの入力はない（可塑性あり）
- 試し（README §3、protocol の probe）：各本体の t0 − 1 の処理の終わりを複製し（A の複製）、t0 に Receptor A の出来事を
  1 つだけ入れて t0 ＋ 1 ＋ T_w まで進める（可塑性あり）。空の側は本体そのもの。状態への介入（ℐ）はしない
- 確認のための複製（README §7）：各本体の最初と最後の試しで、入力なしの複製（空の側の複製）を窓の終わりまで進める。
  試しの複製を一度も作らない O の双子を、O の本体と同じ終わりまで進める
- 記録（README §8、protocol の records）：比較に使う全状態を、実装の内部表現の値のまま（丸めずに）保存する。
  全状態 ＝ 3 Unit の activity・順応（と、同じ Unit の状態に含まれる不応期の残り・発火の回数）、6 本の重み、
  接続ごとの 2 つの痕跡、次の Pulse に届く駆動（と Delta の数）

この道具は、ほかの実験の道具（world.py など）を読み込まない。脳の設計図のパスは protocol の brain.manifest から読む。
観測の量（ℓ・L・外にあるか・h・補助の量）はここでは計算しない（analyze.py が、操作の確認がすべて成り立ったときだけ計算する）。
"""

import asyncio
import copy
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

# 実験の ID・乱数の流れの名前・並べ替えの数は protocol から読む
EXPERIMENT = PROTOCOL["experiment"]
RNG_SHUFFLE = PROTOCOL["conditions"]["within_trial_shuffles"]["rng"]
K = PROTOCOL["conditions"]["within_trial_shuffles"]["count"]
ROLES = ("A", "B", "C")
BODIES = ("O", "M") + tuple(f"W{i}" for i in range(1, K + 1))
SHUFFLES = BODIES[2:]

# protocol の式・名前の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
PROBES_FIRST = "experience_end + 1"
PROBES_COUNT = "adaptation_tau / pulse_interval_seconds"
WINDOW_PULSES = "adaptation_tau / pulse_interval_seconds"
BODY_RUNS_TO = "probes.first + probes.count - 1 + 1 + window_pulses"
SCHEDULES = {"O": "ordered", "M": "mirrored", "within_trial_shuffles": "shuffled_labels_within_each_trial"}
WITHIN_TRIAL_PROCEDURE = ("for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, shuffle the list "
                          "[A, B, C] once with that stream and assign it to (t_k, t_k + b_offset, t_k + c_offset)")
A_COPY = {"input_at_t0": "receptor_of_role_A", "runs_to": "t0 + 1 + window_pulses", "plasticity": True}
PROBE_BASE = "body_end_of_t0_minus_1"
NULL_SIDE = "body_itself"
WINDOW = "t0 + 2 .. t0 + 1 + window_pulses"
CENSOR = "t0 + 2 + window_pulses"

UNIT_FIELDS = ("activity", "adaptation", "refractory_remaining", "fire_count")
CONNECTION_FIELDS = ("weight", "pre_trace", "post_trace")
FULL_STATE_FIELDS = ("pulse", "units", "connections", "drives", "deltas")   # protocol の records.full_state_fields


# ---- 時間の流れ（Plan）-------------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """経験・試し・窓・本体の終わり。本番・smoke は plan_from(protocol) だけを使う（run.py は Plan を受け取らない）。

    契約テストは同じ式で値だけを小さくした Plan（make_plan）を使う。analyze.py は、本番・smoke の生の記録の Plan が
    plan_from(protocol) と完全に同じことを確かめる。
    """
    trials: int
    experience_end: PulseNumber
    probes: tuple[PulseNumber, ...]
    window: int
    body_end: PulseNumber

    @property
    def states_from(self) -> PulseNumber:
        """本体の各 Pulse の終わりの全状態を記録し始める Pulse（protocol records.per_body の 11999 ＝ experience_end − 1）。"""
        return self.experience_end - 1

    def as_dict(self) -> dict:
        d = asdict(self)
        d["probes"] = list(self.probes)
        return d


def make_plan(protocol: dict, trials: int, probe_count: int, window: int) -> Plan:
    """protocol の式（experience_end・probes・body_runs_to）を、与えた試行の数・試しの数・窓の長さに当てはめる。"""
    tl = protocol["timeline"]
    if (tl["experience_end"] != EXPERIENCE_END or tl["probes"]["first"] != PROBES_FIRST
            or tl["probes"]["every"] != 1 or tl["body_runs_to"] != BODY_RUNS_TO):
        raise ValueError("timeline の式が道具と違う")
    if trials < 1 or probe_count < 1 or window < 1:
        raise ValueError("試行・試し・窓の数は 1 以上")
    t = tl["trials"]
    end = t["first"] - 1 + trials * t["every"]
    first = end + 1
    probes = tuple(range(first, first + probe_count))
    return Plan(trials=trials, experience_end=end, probes=probes, window=window,
                body_end=first + probe_count - 1 + 1 + window)


def _tau_pulses(protocol: dict) -> int:
    exact = manifest_raw(protocol)["defaults"]["dynamics"]["adaptation_tau"] / protocol["timeline"]["pulse_interval_seconds"]
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"adaptation_tau ÷ pulse_interval_seconds が整数でない（{exact}）")
    return n


def plan_from(protocol: dict) -> Plan:
    """protocol の Plan（本番・smoke）：試行 200、試し 12001〜12300、T_w ＝ 300、本体の終わり 12601。"""
    tl = protocol["timeline"]
    if tl["probes"]["count"] != PROBES_COUNT or tl["window_pulses"] != WINDOW_PULSES:
        raise ValueError("probes.count・window_pulses の式が道具と違う")
    n = _tau_pulses(protocol)
    return make_plan(protocol, tl["trials"]["count"], n, n)


def plan_of(d: Mapping) -> Plan:
    """生の記録に書いた Plan を読み戻す。"""
    return Plan(trials=d["trials"], experience_end=d["experience_end"], probes=tuple(d["probes"]),
                window=d["window"], body_end=d["body_end"])


# ---- 役の割り当てと刺激（README §2）----------------------------------------------------------------------

def role_receptors(protocol: dict, seed: int) -> dict[str, ComponentId]:
    order = protocol["stimulus"]["role_orders"][(seed - 1) % 6]
    return dict(zip(ROLES, order))


def role_units(protocol: dict, seed: int) -> dict[str, ComponentId]:
    to_unit = protocol["brain"]["receptors"]
    return {role: to_unit[r] for role, r in role_receptors(protocol, seed).items()}


def trial_starts(protocol: dict, plan: Plan) -> list[PulseNumber]:
    t = protocol["timeline"]["trials"]
    return [t["first"] + k * t["every"] for k in range(plan.trials)]


def ordered_labels(protocol: dict, plan: Plan) -> list[tuple[PulseNumber, str]]:
    """O：A を 1 ＋ 60k、B をその b_offset 後、C をその c_offset 後。"""
    s = protocol["stimulus"]
    out = []
    for start in trial_starts(protocol, plan):
        out += [(start, "A"), (start + s["b_offset"], "B"), (start + s["c_offset"], "C")]
    return sorted(out)


def mirrored_labels(protocol: dict, plan: Plan) -> list[tuple[PulseNumber, str]]:
    """M：O と同じ時刻に、A を 1 ＋ 60k、C をその b_offset 後、B をその c_offset 後（O の B と C の入れ替え）。"""
    swap = {"A": "A", "B": "C", "C": "B"}
    return [(t, swap[x]) for t, x in ordered_labels(protocol, plan)]


def rng_name(seed: int, i: int) -> str:
    return RNG_SHUFFLE.format(i=i, seed=seed)


def within_trial_labels(protocol: dict, plan: Plan, seed: int, i: int) -> list[tuple[PulseNumber, str]]:
    """W_i：random.Random(rng_name(seed, i)) の流れを 1 本だけ使い、試行 k ＝ 0, 1, … の順に、リスト [A, B, C] をその流れで
    1 回ずつ shuffle して、試行 k の 3 つの枠（t_k、t_k ＋ b_offset、t_k ＋ c_offset）に置く（README §2、protocol の procedure）。"""
    s = protocol["stimulus"]
    rng = random.Random(rng_name(seed, i))
    out = []
    for start in trial_starts(protocol, plan):
        roles = list(ROLES)
        rng.shuffle(roles)
        out += list(zip((start, start + s["b_offset"], start + s["c_offset"]), roles))
    return sorted(out)


def trial_slots(protocol: dict, plan: Plan) -> list[tuple[PulseNumber, PulseNumber, PulseNumber]]:
    """試行ごとの 3 つの枠の時刻。"""
    s = protocol["stimulus"]
    return [(t, t + s["b_offset"], t + s["c_offset"]) for t in trial_starts(protocol, plan)]


def shuffle_index(body: str) -> int:
    if body not in SHUFFLES:
        raise ValueError(f"{body} は試行の中の並べ替えの本体ではない")
    return int(body[1:])


def labels_of(protocol: dict, plan: Plan, seed: int, body: str) -> list[tuple[PulseNumber, str]]:
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
    """決めた Pulse の番号のときに、中身なしの感覚の出来事を成立させる Receptor（実験の道具）。
    試しでは、複製のほうにだけ inject で予定を足す（過去・今の Pulse には足せない）。"""

    def __init__(self, receptor_id: ComponentId, pulses: Iterable[PulseNumber]) -> None:
        self._receptor_id = receptor_id
        self._pulses = set(pulses)
        self._last_drained: PulseNumber = 0

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self, pulse: PulseNumber) -> tuple[SensoryEvent, ...]:
        self._last_drained = pulse
        return (SensoryEvent(self._receptor_id, pulse, None),) if pulse in self._pulses else ()

    def inject(self, pulse: PulseNumber) -> None:
        if pulse <= self._last_drained:
            raise ValueError(f"{self._receptor_id}: Pulse {pulse} はもう過ぎている（{self._last_drained} まで drain 済み）")
        self._pulses.add(pulse)


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


def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


def plasticity(protocol: dict):
    return parse_neuroarchitecture(manifest_raw(protocol)).plasticity


def initial_connections(protocol: dict) -> dict[str, list[float]]:
    """設計図の、可塑性の対象の接続の出生時の状態 {connection_id: [重み, 0, 0]}。"""
    m = parse_neuroarchitecture(manifest_raw(protocol))
    return {f"{p.source_id}.main->{p.target_id}": [p.weight, 0.0, 0.0] for p in m.projections if p.plastic}


def connection_id(source: ComponentId, target: ComponentId) -> str:
    return f"{source}.main->{target}"


def unit_of(cid: str) -> tuple[str, str]:
    """"s1.main->s2" → ("s1", "s2")。"""
    src, dst = cid.split("->")
    return src.split(".")[0], dst


def receptors_for(protocol: dict, labels: list[tuple[PulseNumber, str]], seed: int) -> dict[ComponentId, ScheduledReceptor]:
    roles = role_receptors(protocol, seed)
    schedule: dict[ComponentId, list[PulseNumber]] = {r: [] for r in protocol["brain"]["receptors"]}
    for t, x in labels:
        schedule[roles[x]].append(t)
    return {r: ScheduledReceptor(r, pulses) for r, pulses in schedule.items()}


def build(protocol: dict, labels: list[tuple[PulseNumber, str]], seed: int, body: str, log: ExperimentLog) -> Application:
    """同じ seed の 21 の本体は、同じ出生時の状態（parse_birth_state の seed）から作る。違うのは Receptor の予定だけ。"""
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-{EXPERIMENT}-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=receptors_for(protocol, labels, seed),
        run_metadata={"experiment": EXPERIMENT, "body": body,
                      "receptors": f"ScheduledReceptor（experiments/{HERE.name}/world.py）"},
    )


def advance_to(app: Application, pulse: PulseNumber) -> None:
    """個体を、Pulse `pulse` の処理が終わったところまで進める（すでにそこなら何もしない）。"""
    if app.lifecycle.pulse > pulse:
        raise ValueError(f"Pulse {app.lifecycle.pulse} からは {pulse} へ戻れない")
    if app.lifecycle.pulse < pulse:
        asyncio.run(app.lifecycle.run(max_pulses=pulse))


def clone(app: Application, app_log: ExperimentLog) -> tuple[Application, ExperimentLog]:
    """個体を丸ごと複製する（Unit・接続・Shared Brain State・Receptor の予定・Pulse・時計）。複製は本体と何も共有しない。
    来歴ログだけは複製せず、新しい空のログに差し替える（本体のログを汚さない）。"""
    clone_log = ExperimentLog()
    copied = copy.deepcopy(app, {id(app_log): clone_log})
    return copied, clone_log


def full_state(app: Application) -> dict:
    """全状態（README §8）。値は実装が書き出したもののまま（丸めない）。

    units：Unit → [activity, adaptation, refractory_remaining, fire_count]（UNIT_FIELDS の順）
    connections：接続 → [weight, pre_trace, post_trace]（CONNECTION_FIELDS の順）
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


# ---- 試し（README §3）------------------------------------------------------------------------------------

def a_copy(protocol: dict, plan: Plan, seed: int, app: Application, log: ExperimentLog, t0: PulseNumber,
           deliver: bool = True) -> dict:
    """本体は t0 − 1 まで進んでいること。本体には触らない。

    A の複製：t0 − 1 の終わりを複製し、t0 に Receptor A の出来事を 1 つ入れ、t0 ＋ 1 ＋ T_w まで進める（可塑性あり）。
    deliver は契約テストのためだけにある（False：A の出来事を入れない。本番・smoke の measure_seed は常に True）。
    返す値：{t0, sensory, spikes（t0 から窓の終わりまで）, states: {t0-1（複製の直後）, t0, t0+1, end（窓の終わり）}}
    """
    if app.lifecycle.pulse != t0 - 1:
        raise ValueError(f"試しは Pulse {t0 - 1} まで進んだ本体から作る（今 {app.lifecycle.pulse}）")
    copied, clog = clone(app, log)
    states = {"t0-1": full_state(copied)}
    if deliver:
        copied.receptors[role_receptors(protocol, seed)["A"]].inject(t0)
    advance_to(copied, t0)
    states["t0"] = full_state(copied)
    advance_to(copied, t0 + 1)
    states["t0+1"] = full_state(copied)
    advance_to(copied, t0 + 1 + plan.window)
    states["end"] = full_state(copied)
    return {"t0": t0, "sensory": clog.sensory(), "spikes": clog.spikes(), "states": states}


def empty_side_copy(plan: Plan, app: Application, log: ExperimentLog, t0: PulseNumber) -> dict:
    """空の側の確認の複製：t0 − 1 の終わりを複製し、入力なしで窓の終わりまで 1 Pulse ずつ進め、各 Pulse の終わりの全状態を残す。"""
    if app.lifecycle.pulse != t0 - 1:
        raise ValueError(f"空の側の複製は Pulse {t0 - 1} まで進んだ本体から作る（今 {app.lifecycle.pulse}）")
    copied, clog = clone(app, log)
    states = [full_state(copied)]
    for t in range(t0, t0 + 2 + plan.window):
        advance_to(copied, t)
        states.append(full_state(copied))
    return {"t0": t0, "sensory": clog.sensory(), "spikes": clog.spikes(), "states_from": t0 - 1, "states": states}


# ---- 1 つの本体（README §3・§8）--------------------------------------------------------------------------

def run_body(protocol: dict, plan: Plan, seed: int, body: str, labels: list, snapshot_at: Iterable[int],
             probes: bool = True, deliver: bool = True) -> dict:
    """1 つの本体を出生から plan.body_end まで進める。probes が True なら各 t0 で A の複製を作り、最初と最後の試しで
    空の側の複製を作る（False は O の双子：試しの複製を一度も作らない）。

    snapshot_at：経験の途中で全状態を残す Pulse（札が O と最初に違う Pulse の 1 つ前。§7 の確認のため）。
    """
    log = ExperimentLog()
    app = build(protocol, labels, seed, body, log)
    rec = {"body": body, "birth": full_state(app), "dynamics": unit_dynamics(app)}
    snaps: dict[str, dict] = {}
    for t in sorted({t for t in snapshot_at if 0 < t < plan.states_from}):
        advance_to(app, t)
        snaps[str(t)] = full_state(app)
    rec["before_divergence"] = snaps
    if not probes:                                   # O の双子
        advance_to(app, plan.experience_end)
        rec["state_experience_end"] = full_state(app)
        advance_to(app, plan.body_end)
        rec["state_end"] = full_state(app)
        rec |= {"sensory": log.sensory(), "spikes": log.spikes()}
        return rec
    advance_to(app, plan.states_from)
    states = [full_state(app)]
    probe_set, edges = set(plan.probes), {plan.probes[0], plan.probes[-1]}
    copies, empty = [], []
    for t in range(plan.states_from + 1, plan.body_end + 1):
        if t in probe_set:                           # 本体は t − 1 の終わり
            copies.append(a_copy(protocol, plan, seed, app, log, t, deliver))
            if t in edges:
                empty.append(empty_side_copy(plan, app, log, t))
        advance_to(app, t)
        states.append(full_state(app))
    rec |= {"sensory": log.sensory(), "spikes": log.spikes(), "states_from": plan.states_from, "states": states,
            "probes": copies, "empty_side": empty}
    return rec


# ---- 1 個体の測定（run.py と契約テストが同じ関数を使う）------------------------------------------------------

def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    """同じ seed から 21 の本体と O の双子を測る。生の記録だけを返す（観測の量は計算しない）。"""
    plan = plan if plan is not None else plan_from(protocol)
    labels = {b: labels_of(protocol, plan, seed, b) for b in BODIES}
    diverge = {b: first_label_divergence(labels["O"], labels[b]) for b in BODIES if b != "O"}
    before = {d - 1 for d in diverge.values() if d is not None}
    bodies = {}
    for b in BODIES:
        snap = before if b == "O" else ({diverge[b] - 1} if diverge[b] is not None else set())
        bodies[b] = run_body(protocol, plan, seed, b, labels[b], snap) | {
            "labels": [list(x) for x in labels[b]], "rng": rng_name(seed, shuffle_index(b)) if b in SHUFFLES else None,
            "first_divergence_from_O": diverge.get(b)}
    twin = run_body(protocol, plan, seed, "O_twin", labels["O"], (), probes=False)
    return {"seed": seed, "plan": plan.as_dict(),
            "roles": {"receptors": role_receptors(protocol, seed), "units": role_units(protocol, seed)},
            "bodies": bodies, "O_twin": twin}
