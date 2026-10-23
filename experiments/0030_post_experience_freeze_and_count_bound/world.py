"""実験 0030 の道具（確定した事前登録 v0.1 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

F と N^cnt（README §0〜§3）：設計図・世界・役の割り当て・経験は 0028 と同じ（C0、可塑性あり）。試し・入れ替えは置かない。

- 自然な本体 21（README §2.1、protocol の conditions）：同じ seed（同じ出生時の状態）から、O（順序あり）・M（鏡）・W1〜W19（試行の中の
  並べ替え：i ごとに protocol の乱数の流れ conditions.within_trial_shuffles.rng を 1 本だけ使い、試行 k ＝ 0, 1, … の順に
  [A, B, C] を 1 回ずつ並べ替えて、試行 k の 3 つの枠に置く）。経験は Pulse 1〜experience_end、その後はどの本体にも外からの
  入力はない（可塑性あり）。各本体を body_end（主の区間の終わり）まで進める
- 可塑性を止める時刻 T_0（README §2.2、protocol の freeze.time）：T_0 の窓（最後の刺激の次〜経験の終わり）のうち、自然な 21 本体の
  どれでも、どの Unit も発火していない最後の Pulse。窓の中になければ T_0 はない
- T_0 がない個体（README §2.6）：raw の freeze.t0_exists ＝ false・freeze.t0 ＝ null・freeze.window_witness（窓の各 Pulse で最初に
  発火した自然な本体と Unit）、自然な本体の state_t0 ＝ null、F 本体・確認の本体は空の配列。T_0 がないことは有効な結果
- F 本体 F(b)（README §2.3・§2.4、protocol の f_variant）：C0 の設計図を YAML として読んだ値から、s のあいだの 6 本の plastic: true
  だけを除き、6 本の weight を b の T_0 の処理の終わりの重みにした設計図の変種（メモリの上だけで作る）で、同じ出生時の状態から個体を
  組み立て、b の T_0 の終わりの 3 Unit の状態を Core の公開の import_state で写して、T_0 ＋ 1 から body_end まで入力なしで進める。
  組み立てた個体は Pulse 0 から数えるので、記録では Pulse の番号を T_0 ＋ 経過にそろえる（発火の時刻・全状態の pulse・駆動の成立の
  Pulse）。前提 P-τ：12001 以後の更新は状態だけで決まる（Pulse の番号は Receptor の予定と記録にしか使われず、F 本体には予定がない）
- 組み立ての確認の本体 R(O)（README §2.4）：同じ組み立て方で、C0 の設計図のまま（可塑性あり）、O の T_0 の Unit の状態と接続の状態
  （重みと痕跡）を公開の import_state で写した本体。自然な O の軌道を再現するはず
- 記録（README §8、protocol の records）：比較に使う全状態を、実装の内部表現の値のまま（丸めずに）保存する。**判定の量（主の事象）は
  raw に書かない**（protocol の records.no_judgment_quantities_in_raw。analyze.py が、操作の確認がすべて成り立ったときだけ計算する）

この道具は、ほかの実験の道具（world.py など）を読み込まない。脳の設計図のパスは protocol の brain.manifest から読む。
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
BODIES = ("O", "M") + tuple(f"W{i}" for i in range(1, K + 1))       # 自然な本体 21
SHUFFLES = BODIES[2:]
REFERENCE = SHUFFLES                                                 # protocol の freeze.reference_bodies（K ＝ 19）
CONTROL = "R_O"                                                      # protocol の f_variant.rebuild_control.body

# protocol の式・名前の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
LAST_STIMULUS = "trials.first + (trials.count - 1) * trials.every + c_offset"
DELAY_MULTIPLE = 5                                                   # 0027〜0029 と同じ倍数（新しく選んだ値ではない）
DELAY = f"{DELAY_MULTIPLE} * adaptation_tau / pulse_interval_seconds"
COUNT_WINDOW_MAIN = {"first": "experience_end + delay + 1", "length": "trials.count * trials.every",
                     "last": "count_window_main.first + count_window_main.length - 1"}
FREEZE_WINDOW = {"first": "last_stimulus + 1", "last": "experience_end"}
BODY_RUNS_TO = "count_window_main.last"
SCHEDULES = {"O": "ordered", "M": "mirrored", "within_trial_shuffles": "shuffled_labels_within_each_trial"}
WITHIN_TRIAL_PROCEDURE = ("for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, shuffle the list "
                          "[A, B, C] once with that stream and assign it to (t_k, t_k + b_offset, t_k + c_offset)")
MIRROR = {"A": "A", "B": "C", "C": "B"}
FREEZE_TIME_RULE = ("T_0 = max{ t in [freeze_window.first, freeze_window.last] : no Unit fired at Pulse t in any of the 21 natural "
                    "bodies }")
F_BODIES = ("for each natural body b in [O, M, W1..W19]: build F(b) from f_variant with b's weights at end of T_0, copy b's unit "
            "state at end of T_0, run T_0 + 1 .. body_runs_to without plasticity")
F_EDIT = ("remove plastic: true from the six s-s projections and set each s-s weight to the original body's connection weight at the "
          "end of T_0 (value as recorded); all other YAML settings and wiring identical")
PULSE_NUMBERING = "absolute t = T_0 + elapsed pulses of the rebuilt individual (spikes, full-state pulse, drive created_pulse)"
REBUILD_CONSTRUCTION = ("same rebuild as F(O) but keep the C0 manifest (plastic) and copy O's unit state and full connection state "
                        "(weights and traces) at end of T_0 via public import_state")

UNIT_FIELDS = ("activity", "adaptation", "refractory_remaining", "fire_count")
CONNECTION_FIELDS = ("weight", "pre_trace", "post_trace")
FULL_STATE_FIELDS = ("pulse", "units", "connections", "drives", "deltas")   # protocol の records.full_state_fields


# ---- 時間の流れ（Plan）-------------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """経験・T_0 の窓・主の区間・本体の終わり。本番・smoke は plan_from(protocol) だけを使う（run.py は Plan を受け取らない）。

    契約テストは同じ式で値だけを小さくした Plan（make_plan）を使う。T_0 がない個体の契約テストのためだけに、T_0 の窓を
    dataclasses.replace で狭めた Plan も使う（check_plan が、窓が最後の刺激の後・経験の終わりまでにあることを確かめる）。
    analyze.py は、本番・smoke の生の記録の Plan が plan_from(protocol) と完全に同じことを確かめる。
    """
    trials: int
    experience_end: PulseNumber
    last_stimulus: PulseNumber
    delay: int
    freeze_window: tuple[PulseNumber, PulseNumber]   # T_0 を探す窓 [lo, hi]
    main: tuple[PulseNumber, PulseNumber]            # 主の区間 [S, E]
    body_end: PulseNumber
    first_stimulus: tuple[PulseNumber, PulseNumber]   # 最初の刺激の Pulse とその次（確認のための全状態）

    @property
    def pre_main(self) -> PulseNumber:
        """主の区間の始まりの 1 つ前（protocol の records の full_state_13500）。"""
        return self.main[0] - 1

    @property
    def snapshots(self) -> tuple[PulseNumber, PulseNumber, PulseNumber]:
        """自然な本体の全状態を残す時点のうち T_0 を除くもの（full_state_12000・13500・25500）。"""
        return self.experience_end, self.pre_main, self.body_end

    @property
    def rebuilt_snapshots(self) -> tuple[PulseNumber, PulseNumber]:
        """F 本体・確認の本体の全状態を残す時点（full_state_13500・25500）。"""
        return self.pre_main, self.body_end

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("freeze_window", "main", "first_stimulus"):
            d[k] = list(d[k])
        return d


def check_plan(plan: Plan) -> None:
    """T_0 の窓が最後の刺激の後・経験の終わりまでにあり（F 本体に Receptor の予定が残らない）、主の区間の前にあること。"""
    lo, hi = plan.freeze_window
    if not plan.last_stimulus < lo <= hi <= plan.experience_end < plan.pre_main:
        raise ValueError(f"T_0 の窓 {lo}〜{hi} が、最後の刺激 {plan.last_stimulus} の後・経験の終わり {plan.experience_end} までにない")
    if not plan.main[0] <= plan.main[1] == plan.body_end:
        raise ValueError("主の区間・本体の終わりが想定と違う")


def make_plan(protocol: dict, trials: int, delay: int) -> Plan:
    """protocol の式（experience_end・last_stimulus・主の区間・T_0 の窓・body_runs_to）を、与えた試行の数・遅れに当てはめる。"""
    tl = protocol["timeline"]
    if (tl["experience_end"] != EXPERIENCE_END or tl["last_stimulus"] != LAST_STIMULUS or tl["count_window_main"] != COUNT_WINDOW_MAIN
            or tl["freeze_window"] != FREEZE_WINDOW or tl["body_runs_to"] != BODY_RUNS_TO):
        raise ValueError("timeline の式が道具と違う")
    if trials < 1 or delay < 1:
        raise ValueError("試行の数・遅れは 1 以上")
    t, s = tl["trials"], protocol["stimulus"]
    end = t["first"] - 1 + trials * t["every"]
    last = t["first"] + (trials - 1) * t["every"] + s["c_offset"]
    main = (end + delay + 1, end + delay + trials * t["every"])
    plan = Plan(trials=trials, experience_end=end, last_stimulus=last, delay=delay, freeze_window=(last + 1, end), main=main,
                body_end=main[1], first_stimulus=(t["first"], t["first"] + 1))
    check_plan(plan)
    return plan


def _tau_pulses(protocol: dict) -> int:
    exact = manifest_raw(protocol)["defaults"]["dynamics"]["adaptation_tau"] / protocol["timeline"]["pulse_interval_seconds"]
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"adaptation_tau ÷ pulse_interval_seconds が整数でない（{exact}）")
    return n


def plan_from(protocol: dict) -> Plan:
    """protocol の Plan（本番・smoke）：試行 200、経験の終わり 12000、T_0 の窓 11972〜12000、主の区間 13501〜25500、終わり 25500。"""
    tl = protocol["timeline"]
    if tl["delay"] != DELAY:
        raise ValueError("delay の式が道具と違う")
    return make_plan(protocol, tl["trials"]["count"], DELAY_MULTIPLE * _tau_pulses(protocol))


def plan_of(d: Mapping) -> Plan:
    """生の記録に書いた Plan を読み戻す。"""
    return Plan(trials=d["trials"], experience_end=d["experience_end"], last_stimulus=d["last_stimulus"], delay=d["delay"],
                freeze_window=tuple(d["freeze_window"]), main=tuple(d["main"]), body_end=d["body_end"],
                first_stimulus=tuple(d["first_stimulus"]))


def find_freeze_time(spikes_by_body: Mapping[str, Mapping[str, list[int]]], lo: PulseNumber, hi: PulseNumber) -> PulseNumber | None:
    """README §2.2：T_0 ＝ 窓 [lo, hi] のうち、どの本体でも、どの Unit も発火していない最後の Pulse（なければ None）。
    自然な本体の発火の列だけで決まり、判定の量を見ない。"""
    fired = {p for sp in spikes_by_body.values() for ps in sp.values() for p in ps if lo <= p <= hi}
    quiet = [t for t in range(lo, hi + 1) if t not in fired]
    return max(quiet) if quiet else None


def window_witness(spikes_by_body: Mapping[str, Mapping[str, list[int]]], units: Iterable[str], lo: PulseNumber,
                   hi: PulseNumber) -> list[dict]:
    """README §2.6：T_0 がないことの根拠。窓の各 Pulse（昇順）について、その Pulse に発火した自然な本体と Unit のうち、本体を
    spikes_by_body の順（O・M・W1〜W19）、Unit を units の順（s1・s2・s3）に見て最初のもの {pulse, body, unit}。
    窓のどれかの Pulse に発火がなければ ValueError（T_0 があるので、根拠を作らない）。"""
    units = tuple(units)
    sets = {b: {u: set(sp.get(u, ())) for u in units} for b, sp in spikes_by_body.items()}
    out = []
    for t in range(lo, hi + 1):
        first = next(((b, u) for b in sets for u in units if t in sets[b][u]), None)
        if first is None:
            raise ValueError(f"Pulse {t} にどの本体も発火していない（T_0 がある）")
        out.append({"pulse": t, "body": first[0], "unit": first[1]})
    return out


# ---- 役の割り当てと刺激（README §2.1）----------------------------------------------------------------------

def role_receptors(protocol: dict, seed: int) -> dict[str, ComponentId]:
    order = protocol["stimulus"]["role_orders"][(seed - 1) % 6]
    return dict(zip(ROLES, order))


def role_units(protocol: dict, seed: int) -> dict[str, ComponentId]:
    to_unit = protocol["brain"]["receptors"]
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

    def spikes(self, offset: int = 0) -> dict[str, list[int]]:
        """Unit → 発火した Pulse の列（Pulse の順）。offset は組み立て直した個体の Pulse の番号を絶対の番号にそろえる差。"""
        out: dict[str, list[int]] = {}
        for e in self.events:
            if e.type == RuntimeEventType.ACTIVITY:
                out.setdefault(e.data["unit_id"], []).append(e.pulse + offset)
        return out

    def sensory(self, offset: int = 0) -> list[list]:
        return [[e.pulse + offset, e.data["receptor_id"]] for e in self.events if e.type == RuntimeEventType.SENSORY]


def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


def plasticity(protocol: dict):
    return parse_neuroarchitecture(manifest_raw(protocol)).plasticity


def initial_connections(protocol: dict) -> dict[str, list[float]]:
    """設計図の、可塑性の対象の接続の出生時の状態 {connection_id: [重み, 0, 0]}。"""
    m = parse_neuroarchitecture(manifest_raw(protocol))
    return {connection_id(p.source_id, p.target_id): [p.weight, 0.0, 0.0] for p in m.projections if p.plastic}


def connection_id(source: ComponentId, target: ComponentId) -> str:
    return f"{source}.main->{target}"


def unit_of(cid: str) -> tuple[str, str]:
    """"s1.main->s2" → ("s1", "s2")。"""
    src, dst = cid.split("->")
    return src.split(".")[0], dst


def f_variant_manifest(protocol: dict, weights: Mapping[str, float]) -> dict:
    """README §2.3・§2.4、protocol の f_variant.edit：C0 の設計図を YAML として読んだ値から、s のあいだの 6 本の plastic: true だけを
    除き、6 本の weight を weights（connection_id → 値。記録した値のまま）にした値。ほかの YAML の設定値と配線は変えない。
    ファイルは作らない（parse_neuroarchitecture に渡すだけ）。"""
    units = set(protocol["brain"]["sensory_units"])
    variant = copy.deepcopy(manifest_raw(protocol))
    edited = set()
    for p in variant["projections"]:
        src = p["from"].split(".")[0]
        if src in units and p["to"] in units:
            if p.get("plastic") is not True:
                raise ValueError(f"{p['from']} → {p['to']} が C0 の設計図で可塑性の対象ではない")
            cid = connection_id(src, p["to"])
            if cid not in weights:
                raise ValueError(f"{cid} の重みがない")
            del p["plastic"]
            p["weight"] = weights[cid]
            edited.add(cid)
    if edited != set(weights) or len(edited) != 6:
        raise ValueError(f"替えた接続 {sorted(edited)} が、重みの接続 {sorted(weights)} の 6 本と違う")
    return variant


def receptors_for(protocol: dict, labels: list[tuple[PulseNumber, str]], seed: int) -> dict[ComponentId, ScheduledReceptor]:
    roles = role_receptors(protocol, seed)
    schedule: dict[ComponentId, list[PulseNumber]] = {r: [] for r in protocol["brain"]["receptors"]}
    for t, x in labels:
        schedule[roles[x]].append(t)
    return {r: ScheduledReceptor(r, pulses) for r, pulses in schedule.items()}


def build(protocol: dict, labels: list[tuple[PulseNumber, str]], seed: int, body: str, log: ExperimentLog,
          manifest: Mapping | None = None) -> Application:
    """同じ seed の本体は、同じ出生時の状態（parse_birth_state の seed）から作る。違うのは Receptor の予定と、F 本体の設計図の変種
    だけ。Unit の出生時の値の乱数は Unit の並びの順に消費されるので、接続の plastic・weight の違いは Unit の力学に影響しない
    （F の組み立ての確認で、力学が自然な本体と同じことを確かめる）。"""
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(dict(manifest) if manifest is not None else manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-{EXPERIMENT}-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=receptors_for(protocol, labels, seed),
        run_metadata={"experiment": EXPERIMENT, "body": body,
                      "receptors": f"ScheduledReceptor（experiments/{HERE.name}/world.py）"},
    )


def advance_to(app: Application, pulse: PulseNumber) -> None:
    """個体を、Pulse `pulse`（その個体の Pulse の番号）の処理が終わったところまで進める（すでにそこなら何もしない）。"""
    if app.lifecycle.pulse > pulse:
        raise ValueError(f"Pulse {app.lifecycle.pulse} からは {pulse} へ戻れない")
    if app.lifecycle.pulse < pulse:
        asyncio.run(app.lifecycle.run(max_pulses=pulse))


def full_state(app: Application, offset: int = 0) -> dict:
    """全状態（README §8）。値は実装が書き出したもののまま（丸めない）。欄は FULL_STATE_FIELDS の 5 つ。

    units：Unit → [activity, adaptation, refractory_remaining, fire_count]（UNIT_FIELDS の順）
    connections：可塑的な接続 → [weight, pre_trace, post_trace]（CONNECTION_FIELDS の順。F 本体には可塑的な接続がないので空の辞書）
    drives：次の Pulse に届く駆動 [[送り手, 受け手, 重み, 成立の Pulse]]（並べ替えた列）。deltas：残っている Delta の数
    offset：組み立て直した個体の Pulse の番号を絶対の番号にそろえる差（pulse と駆動の成立の Pulse に足す。自然な本体は 0）
    """
    units = {}
    for u in app.units.all():
        s = u.export_state()
        units[u.unit_id] = [s[f] for f in UNIT_FIELDS]
    conns = {cid: [v[f] for f in CONNECTION_FIELDS] for cid, v in app.connections.export_state().items()}
    bs = app.pulse_runtime.brain_state
    drives = sorted([d.source_id, d.target_id, d.weight, d.created_pulse + offset] for d in bs.drives)
    return {"pulse": app.lifecycle.pulse + offset, "units": units, "connections": conns, "drives": drives, "deltas": len(bs.deltas)}


def unit_dynamics(app: Application) -> dict:
    """Unit の力学の値（出生時の状態で決まり、変わらない）。"""
    return {u.unit_id: u.export_state()["dynamics"] for u in app.units.all()}


def import_unit_states(app: Application, state: Mapping) -> None:
    """state（full_state の形）の 3 Unit の状態を、Core の公開の GenericCognitiveUnit.import_state で写す。"""
    for u in app.units.all():
        v = state["units"][u.unit_id]
        u.import_state({f: v[i] for i, f in enumerate(UNIT_FIELDS)})


# ---- 自然な本体（README §2.1・§8）--------------------------------------------------------------------------

def run_body(protocol: dict, plan: Plan, seed: int, body: str, labels: list, before_divergence: Iterable[int]) -> dict:
    """1 つの自然な本体を出生から plan.body_end まで進める（試しの複製は作らない）。

    before_divergence：経験の途中で全状態を残す Pulse（札が O と最初に違う Pulse の 1 つ前。§7 の確認のため）。
    最初の刺激の Pulse とその次、経験の終わり・主の区間の始まりの 1 つ前・本体の終わりの全状態を残す。
    T_0 の窓の各 Pulse の終わりの全状態を rec["window_states"] に一時的に残す（T_0 が決まった後に、T_0 のものだけを state_t0 として
    残す：measure_seed）。
    """
    log = ExperimentLog()
    app = build(protocol, labels, seed, body, log)
    rec = {"body": body, "birth": full_state(app), "dynamics": unit_dynamics(app)}
    lo, hi = plan.freeze_window
    want_div = {t for t in before_divergence if 0 < t < plan.experience_end}
    keep = want_div | set(plan.first_stimulus) | set(plan.snapshots)
    window = set(range(lo, hi + 1))
    snaps: dict[int, dict] = {}
    window_states: dict[int, dict] = {}
    for t in sorted(keep | window):
        advance_to(app, t)
        st = full_state(app)
        if t in keep:
            snaps[t] = st
        if t in window:
            window_states[t] = st
    if app.lifecycle.pulse != plan.body_end:
        raise ValueError(f"本体が {plan.body_end} で終わっていない（{app.lifecycle.pulse}）")
    rec["first_stimulus"] = {str(t): snaps[t] for t in plan.first_stimulus}
    rec["before_divergence"] = {str(t): snaps[t] for t in sorted(want_div)}
    rec["states"] = {str(t): snaps[t] for t in plan.snapshots}
    rec |= {"sensory": log.sensory(), "spikes": log.spikes(), "window_states": window_states}
    return rec


# ---- F 本体・組み立ての確認の本体（README §2.3・§2.4・§8）-----------------------------------------------------------

def run_rebuilt(protocol: dict, plan: Plan, seed: int, name: str, t0: PulseNumber, state_t0: Mapping, plastic: bool) -> dict:
    """自然な本体の T_0 の終わりの状態 state_t0 から、個体を組み立て直して T_0 ＋ 1 から本体の終わりまで、入力なしで進める。

    plastic が False（F 本体）：設計図は f_variant_manifest（6 本の重みを state_t0 の重みに固定、可塑性なし）。Unit の状態だけを写す。
    plastic が True（確認の本体 R(O)）：設計図は C0 のまま。Unit の状態と接続の状態（重みと痕跡）を写す。
    どちらも Receptor の予定は空。記録の Pulse の番号は T_0 ＋ 経過（offset ＝ T_0）。
    """
    weights = {cid: v[0] for cid, v in state_t0["connections"].items()}
    manifest = None if plastic else f_variant_manifest(protocol, weights)
    log = ExperimentLog()
    app = build(protocol, [], seed, name, log, manifest)
    if app.lifecycle.pulse != 0 or app.pulse_runtime.brain_state.drives or app.pulse_runtime.brain_state.deltas:
        raise ValueError("組み立てた個体が Pulse 0・駆動なし・Delta なしで始まっていない")
    import_unit_states(app, state_t0)
    if plastic:
        app.connections.import_state({cid: dict(zip(CONNECTION_FIELDS, v)) for cid, v in state_t0["connections"].items()})
    rec: dict = {"dynamics": unit_dynamics(app), "start": full_state(app, t0)}
    states = {}
    for t in plan.rebuilt_snapshots:
        advance_to(app, t - t0)
        states[str(t)] = full_state(app, t0)
    if app.lifecycle.pulse + t0 != plan.body_end:
        raise ValueError(f"組み立て直した本体が {plan.body_end} で終わっていない（{app.lifecycle.pulse + t0}）")
    rec |= {"states": states, "sensory": log.sensory(t0), "spikes": log.spikes(t0)}
    if not plastic:
        rec["frozen_weights"] = weights
    return rec


# ---- 1 個体の測定（run.py と契約テストが同じ関数を使う）------------------------------------------------------

def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    """同じ seed から、自然な本体 21 と、（T_0 があれば）F 本体 21 と確認の本体 R(O) を測る。
    生の記録だけを返す（観測の量・判定の量は計算しない）。"""
    plan = plan if plan is not None else plan_from(protocol)
    check_plan(plan)
    lo, hi = plan.freeze_window
    labels = {b: labels_of(protocol, plan, seed, b) for b in BODIES}
    diverge = {b: first_label_divergence(labels["O"], labels[b]) for b in BODIES if b != "O"}
    before = {d - 1 for d in diverge.values() if d is not None}
    natural = {}
    for b in BODIES:
        snap = before if b == "O" else ({diverge[b] - 1} if diverge[b] is not None else set())
        natural[b] = run_body(protocol, plan, seed, b, labels[b], snap) | {
            "labels": [list(x) for x in labels[b]], "rng": rng_name(seed, shuffle_index(b)) if b in SHUFFLES else None,
            "first_divergence_from_O": diverge.get(b)}
    spikes = {b: natural[b]["spikes"] for b in BODIES}
    t0 = find_freeze_time(spikes, lo, hi)
    for b in BODIES:
        window_states = natural[b].pop("window_states")
        natural[b]["state_t0"] = window_states[t0] if t0 is not None else None
    f_bodies: list[dict] = []
    controls: list[dict] = []
    if t0 is None:
        freeze = {"t0_exists": False, "t0": None,
                  "window_witness": window_witness(spikes, protocol["brain"]["sensory_units"], lo, hi)}
    else:
        for b in BODIES:
            f_bodies.append({"original_body": b} | run_rebuilt(protocol, plan, seed, f"F({b})", t0, natural[b]["state_t0"], False))
        controls.append({"name": CONTROL} | run_rebuilt(protocol, plan, seed, CONTROL, t0, natural["O"]["state_t0"], True))
        freeze = {"t0_exists": True, "t0": t0, "window_witness": None}
    return {"seed": seed, "plan": plan.as_dict(),
            "roles": {"receptors": role_receptors(protocol, seed), "units": role_units(protocol, seed)},
            "freeze_window": [lo, hi], "freeze": freeze,
            "natural_bodies": natural, "f_bodies": f_bodies, "control_bodies": controls}
