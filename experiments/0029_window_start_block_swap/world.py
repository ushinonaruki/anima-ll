"""実験 0029 の道具（確定した事前登録 v0.2 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

L3 の担い手 Wt・U（README §0〜§2）：設計図・世界・役の割り当て・経験は 0028 と同じ（C0、可塑性あり）。試しは置かない。

- 自然な本体 22（README §2.1、protocol の conditions）：同じ seed（同じ出生時の状態）から、O（順序あり）・M（鏡）・W1〜W20（試行の中の
  並べ替え：i ごとに protocol の乱数の流れ conditions.within_trial_shuffles.rng を 1 本だけ使い、試行 k ＝ 0, 1, … の順に
  [A, B, C] を 1 回ずつ並べ替えて、試行 k の 3 つの枠に置く）。経験は Pulse 1〜experience_end、その後はどの本体にも外からの
  入力はない（可塑性あり）。各本体を body_end（主の区間の終わり）まで進める
- 入れ替える時刻 τ（README §2.2、protocol の intervention.swap_time）：τ の窓（主の区間の始まりの直前の trials.every の Pulse）の
  うち、自然な 22 本体のどれでも、どの Unit も発火していない最後の Pulse。窓の中になければ τ はない
- τ がない個体（README §2.6）：raw の swap.tau_exists ＝ false・swap.tau ＝ null・swap.window_witness（窓の各 Pulse で最初に
  発火した自然な本体と Unit）、自然な本体の state_tau ＝ null、入れ替えた本体・確認の本体は空の配列、8 つの事象はすべて false
  （not_outside_reason ＝ no_tau）。τ がないことは有効な結果で、記録の欠け・操作の失敗ではない
- 入れ替えた本体 Y^c(d)（README §2.3、protocol の intervention.swapped_bodies）：受け手 W20 の τ の処理の終わりの状態を複製し、
  塊 c の欄だけをドナー d（O・M・W1〜W19）の τ の終わりの値に替え（Core の公開の import_state だけを使う：README §2.5）、
  τ ＋ 1 から body_end まで可塑性ありで進める。塊 2 × ドナー 21 ＝ 42 本体
- 確認の本体（README §2.3・§7）：両方の塊を O の値にした本体（full_swap）と、W20 自身の値にした本体（null_swap）
- 記録（README §8、protocol の records）：比較に使う全状態を、実装の内部表現の値のまま（丸めずに）保存する

この道具は、ほかの実験の道具（world.py など）を読み込まない。脳の設計図のパスは protocol の brain.manifest から読む。
観測の量（N・Δ・D・外にあるか・h・補助の量）はここでは計算しない（analyze.py が、操作の確認がすべて成り立ったときだけ計算する）。
τ がある個体の raw の swap.events は null（事象は analyze.py が計算する）。τ がない個体の 8 つの事象は、定義（README §2.6）から
すべて false なので、raw にそのまま書く（現象の値を使わない）。
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
BODIES = ("O", "M") + tuple(f"W{i}" for i in range(1, K + 1))       # 自然な本体 22
SHUFFLES = BODIES[2:]
RECIPIENT = f"W{K}"                                                  # W20（protocol の intervention.recipient）
REFERENCE = tuple(f"W{i}" for i in range(1, K))                     # W1〜W19（protocol の intervention.reference_donors）
DONORS = ("O", "M") + REFERENCE                                      # protocol の intervention.donors
BLOCK_NAMES = ("weights", "units")
FAMILY_OF = {"weights": "Wt", "units": "U"}                          # protocol の intervention.blocks.<塊>.family
CONTROLS = ("full_swap", "null_swap")

# protocol の式・名前の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
DELAY_MULTIPLE = 5                                                   # 0027・0028 と同じ倍数（新しく選んだ値ではない）
DELAY = f"{DELAY_MULTIPLE} * adaptation_tau / pulse_interval_seconds"
COUNT_WINDOW_MAIN = {"first": "experience_end + delay + 1", "length": "trials.count * trials.every",
                     "last": "count_window_main.first + count_window_main.length - 1"}
SWAP_WINDOW = {"first": "count_window_main.first - trials.every", "last": "count_window_main.first - 1"}
BODY_RUNS_TO = "count_window_main.last"
SCHEDULES = {"O": "ordered", "M": "mirrored", "within_trial_shuffles": "shuffled_labels_within_each_trial"}
WITHIN_TRIAL_PROCEDURE = ("for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, shuffle the list "
                          "[A, B, C] once with that stream and assign it to (t_k, t_k + b_offset, t_k + c_offset)")
MIRROR = {"A": "A", "B": "C", "C": "B"}
SWAP_TIME_RULE = ("tau = max{ t in [swap_window.first, swap_window.last] : no Unit fired at Pulse t in any of the 22 natural "
                  "bodies }")
SWAPPED_BODIES = ("for each block in blocks, for each donor in donors: clone recipient at end of tau, replace the block by the "
                  "donor's values at end of tau, run tau + 1 .. body_runs_to with plasticity")
FULL_SWAP = "clone W20 at end of tau, replace both blocks by O's values; run to body_runs_to"
NULL_SWAP = "clone W20 at end of tau, replace both blocks by W20's own values; run to body_runs_to"

# τ がない個体の 8 つの事象（README §2.6・§4.1。protocol の quantities.primary.per_individual の名前）
EVENTS = {"Wt": ("O_Delta_AB_above", "O_above", "M_below", "O_and_M_split"),
          "U": ("O_Delta_AB_outside", "O_outside", "M_outside", "O_and_M_opposite_ends")}
NO_TAU_REASON = "no_tau"

UNIT_FIELDS = ("activity", "adaptation", "refractory_remaining", "fire_count")
CONNECTION_FIELDS = ("weight", "pre_trace", "post_trace")
FULL_STATE_FIELDS = ("pulse", "units", "connections", "drives", "deltas")   # protocol の records.full_state_fields
# 塊（README §2.3、protocol の intervention.blocks）：塊 → (Unit の欄, 接続の欄)。発火の回数（fire_count）はどちらの塊にも入らず、
# 受け手のまま（観察用の数で、力学に使わない）
BLOCKS = {"weights": ((), ("weight",)),
          "units": (("activity", "adaptation", "refractory_remaining"), ("pre_trace", "post_trace"))}
KEPT_UNIT_FIELDS = ("fire_count",)


# ---- 時間の流れ（Plan）-------------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """経験・τ の窓・主の区間・本体の終わり。本番・smoke は plan_from(protocol) だけを使う（run.py は Plan を受け取らない）。

    契約テストは同じ式で値だけを小さくした Plan（make_plan）を使う。τ がない個体の契約テストのためだけに、τ の窓を
    dataclasses.replace で狭めた Plan も使う（check_plan が、窓が経験の後・主の区間の前にあることを確かめる）。
    analyze.py は、本番・smoke の生の記録の Plan が plan_from(protocol) と完全に同じことを確かめる。
    """
    trials: int
    experience_end: PulseNumber
    delay: int
    swap_window: tuple[PulseNumber, PulseNumber]   # τ を探す窓 [lo, hi]
    main: tuple[PulseNumber, PulseNumber]          # 主の区間 [S, E]
    body_end: PulseNumber
    first_stimulus: tuple[PulseNumber, PulseNumber]   # 最初の刺激の Pulse とその次（確認のための全状態）

    @property
    def pre_main(self) -> PulseNumber:
        """主の区間の始まりの 1 つ前（protocol の records の full_state_13500）。"""
        return self.main[0] - 1

    @property
    def snapshots(self) -> tuple[PulseNumber, PulseNumber, PulseNumber]:
        """自然な本体の全状態を残す時点のうち τ を除くもの（protocol の records の full_state_12000・13500・25500）。"""
        return self.experience_end, self.pre_main, self.body_end

    @property
    def swapped_snapshots(self) -> tuple[PulseNumber, PulseNumber]:
        """入れ替えた本体・確認の本体の全状態を残す時点（full_state_13500・25500）。"""
        return self.pre_main, self.body_end

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("swap_window", "main", "first_stimulus"):
            d[k] = list(d[k])
        return d


def check_plan(plan: Plan) -> None:
    """τ の窓が経験の後・主の区間の前にあり（入れ替えた本体に Receptor の予定が残らない）、窓が 1 Pulse 以上あること。"""
    lo, hi = plan.swap_window
    if not plan.experience_end < lo <= hi <= plan.pre_main:
        raise ValueError(f"τ の窓 {lo}〜{hi} が、経験の終わり {plan.experience_end} の後・主の区間の前 {plan.pre_main} にない")
    if not plan.pre_main < plan.main[0] <= plan.main[1] == plan.body_end:
        raise ValueError("主の区間・本体の終わりが想定と違う")


def make_plan(protocol: dict, trials: int, delay: int) -> Plan:
    """protocol の式（experience_end・主の区間・τ の窓・body_runs_to）を、与えた試行の数・遅れに当てはめる。
    主の区間の長さは protocol の式どおり trials × trials.every（経験の長さと同じ）、τ の窓は主の区間の直前の trials.every の Pulse。"""
    tl = protocol["timeline"]
    if (tl["experience_end"] != EXPERIENCE_END or tl["count_window_main"] != COUNT_WINDOW_MAIN
            or tl["swap_window"] != SWAP_WINDOW or tl["body_runs_to"] != BODY_RUNS_TO):
        raise ValueError("timeline の式が道具と違う")
    if trials < 1 or delay < 1:
        raise ValueError("試行の数・遅れは 1 以上")
    t = tl["trials"]
    end = t["first"] - 1 + trials * t["every"]
    main = (end + delay + 1, end + delay + trials * t["every"])
    plan = Plan(trials=trials, experience_end=end, delay=delay, swap_window=(main[0] - t["every"], main[0] - 1), main=main,
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
    """protocol の Plan（本番・smoke）：試行 200、経験の終わり 12000、τ の窓 13441〜13500、主の区間 13501〜25500、終わり 25500。"""
    tl = protocol["timeline"]
    if tl["delay"] != DELAY:
        raise ValueError("delay の式が道具と違う")
    return make_plan(protocol, tl["trials"]["count"], DELAY_MULTIPLE * _tau_pulses(protocol))


def plan_of(d: Mapping) -> Plan:
    """生の記録に書いた Plan を読み戻す。"""
    return Plan(trials=d["trials"], experience_end=d["experience_end"], delay=d["delay"], swap_window=tuple(d["swap_window"]),
                main=tuple(d["main"]), body_end=d["body_end"], first_stimulus=tuple(d["first_stimulus"]))


def find_swap_time(spikes_by_body: Mapping[str, Mapping[str, list[int]]], lo: PulseNumber, hi: PulseNumber) -> PulseNumber | None:
    """README §2.2：τ ＝ 窓 [lo, hi] のうち、どの本体でも、どの Unit も発火していない最後の Pulse（なければ None）。
    自然な本体の発火の列だけで決まり、判定の量を見ない。"""
    fired = {p for sp in spikes_by_body.values() for ps in sp.values() for p in ps if lo <= p <= hi}
    quiet = [t for t in range(lo, hi + 1) if t not in fired]
    return max(quiet) if quiet else None


def window_witness(spikes_by_body: Mapping[str, Mapping[str, list[int]]], units: Iterable[str], lo: PulseNumber,
                   hi: PulseNumber) -> list[dict]:
    """README §2.6：τ がないことの根拠。窓の各 Pulse（昇順）について、その Pulse に発火した自然な本体と Unit のうち、本体を
    spikes_by_body の順（O・M・W1〜W20）、Unit を units の順（s1・s2・s3）に見て最初のもの {pulse, body, unit}。
    窓のどれかの Pulse に発火がなければ ValueError（τ があるので、根拠を作らない）。"""
    units = tuple(units)
    sets = {b: {u: set(sp.get(u, ())) for u in units} for b, sp in spikes_by_body.items()}
    out = []
    for t in range(lo, hi + 1):
        first = next(((b, u) for b in sets for u in units if t in sets[b][u]), None)
        if first is None:
            raise ValueError(f"Pulse {t} にどの本体も発火していない（τ がある）")
        out.append({"pulse": t, "body": first[0], "unit": first[1]})
    return out


def no_tau_events() -> dict:
    """τ がない個体の 8 つの事象（README §2.6）：すべて false と、理由 no_tau。"""
    return {fam: {e: False for e in evs} for fam, evs in EVENTS.items()} | {"not_outside_reason": NO_TAU_REASON}


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
    return {connection_id(p.source_id, p.target_id): [p.weight, 0.0, 0.0] for p in m.projections if p.plastic}


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
    """同じ seed の 22 の本体は、同じ出生時の状態（parse_birth_state の seed）から作る。違うのは Receptor の予定だけ。"""
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
    """全状態（README §8）。値は実装が書き出したもののまま（丸めない）。欄は FULL_STATE_FIELDS の 5 つ。

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


# ---- 状態の塊の入れ替え（README §2.3・§2.5）---------------------------------------------------------------------

def apply_swap(app: Application, donor_state: Mapping, blocks: Iterable[str]) -> None:
    """app の今の状態のうち、塊 blocks の欄だけを donor_state（full_state の形）の値に替える。
    Core の公開の GenericCognitiveUnit.import_state と ConnectionStore.import_state だけを使う（README §2.5）。
    ほかの欄（発火の回数・駆動・Delta・Receptor の予定・Pulse）は app のまま。"""
    blocks = tuple(blocks)
    if any(b not in BLOCKS for b in blocks):
        raise ValueError(f"知らない塊 {blocks}")
    unit_fields = {f for b in blocks for f in BLOCKS[b][0]}
    conn_fields = {f for b in blocks for f in BLOCKS[b][1]}
    for u in app.units.all():
        s = u.export_state()
        donor = donor_state["units"][u.unit_id]
        u.import_state({f: (donor[UNIT_FIELDS.index(f)] if f in unit_fields else s[f]) for f in UNIT_FIELDS})
    current = app.connections.export_state()
    if set(current) != set(donor_state["connections"]):
        raise ValueError("ドナーと受け手の接続の集合が違う")
    app.connections.import_state({
        cid: {f: (donor_state["connections"][cid][CONNECTION_FIELDS.index(f)] if f in conn_fields else v[f])
              for f in CONNECTION_FIELDS}
        for cid, v in current.items()})


# ---- 自然な本体（README §2.1・§8）--------------------------------------------------------------------------

def run_body(protocol: dict, plan: Plan, seed: int, body: str, labels: list, before_divergence: Iterable[int],
             keep_clones: bool = False) -> tuple[dict, dict]:
    """1 つの自然な本体を出生から plan.body_end まで進める（試しの複製は作らない）。

    before_divergence：経験の途中で全状態を残す Pulse（札が O と最初に違う Pulse の 1 つ前。§7 の確認のため）。
    最初の刺激の Pulse とその次（plan.first_stimulus）、経験の終わり・主の区間の始まりの 1 つ前・本体の終わりの全状態を残す。
    τ の窓の各 Pulse の終わりの全状態を rec["window_states"] に一時的に残す（τ が決まった後に、τ のものだけを state_tau として
    残す：measure_seed）。keep_clones が True（受け手 W20）なら、窓の各 Pulse の終わりの個体の複製も返す。
    返す値：(記録, {Pulse: (複製, 複製のログ)})
    """
    log = ExperimentLog()
    app = build(protocol, labels, seed, body, log)
    rec = {"body": body, "birth": full_state(app), "dynamics": unit_dynamics(app)}
    lo, hi = plan.swap_window
    want_div = {t for t in before_divergence if 0 < t < plan.experience_end}
    want_first = set(plan.first_stimulus)
    want_states = set(plan.snapshots)
    window = set(range(lo, hi + 1))
    snaps: dict[int, dict] = {}
    window_states: dict[int, dict] = {}
    clones: dict[int, tuple] = {}
    for t in sorted(want_div | want_first | want_states | window):
        advance_to(app, t)
        st = full_state(app)
        if t in want_div | want_first | want_states:
            snaps[t] = st
        if t in window:
            window_states[t] = st
            if keep_clones:
                clones[t] = clone(app, log)
    if app.lifecycle.pulse != plan.body_end:
        raise ValueError(f"本体が {plan.body_end} で終わっていない（{app.lifecycle.pulse}）")
    rec["first_stimulus"] = {str(t): snaps[t] for t in plan.first_stimulus}
    rec["before_divergence"] = {str(t): snaps[t] for t in sorted(want_div)}
    rec["states"] = {str(t): snaps[t] for t in plan.snapshots}
    rec |= {"sensory": log.sensory(), "spikes": log.spikes(), "window_states": window_states}
    return rec, clones


# ---- 入れ替えた本体・確認の本体（README §2.3・§8）---------------------------------------------------------------

def run_swapped(plan: Plan, base: tuple, swap_time: PulseNumber, donor_state: Mapping, blocks: Iterable[str]) -> dict:
    """受け手（base ＝ τ の終わりの受け手の複製とそのログ）をもう一度複製し、塊 blocks の欄をドナーの τ の終わりの値に替えて、
    τ ＋ 1 から本体の終わりまで可塑性ありで進める。受け手の複製 base そのものは変えない。
    全状態は、入れ替えた直後（state_tau）と、主の区間の始まりの 1 つ前・本体の終わり（τ が主の区間の始まりの 1 つ前なら、
    その時点の全状態は入れ替えた直後のもの）。記録の発火・感覚の出来事は τ ＋ 1 以後だけ（複製のログは τ の終わりで空）。"""
    app, log = clone(*base)
    if app.lifecycle.pulse != swap_time:
        raise ValueError(f"受け手の複製が τ（{swap_time}）の終わりにない（{app.lifecycle.pulse}）")
    apply_swap(app, donor_state, blocks)
    rec: dict = {"state_tau": full_state(app)}
    states = {}
    for t in plan.swapped_snapshots:
        advance_to(app, t)
        states[str(t)] = full_state(app)
    return rec | {"states": states, "sensory": log.sensory(), "spikes": log.spikes()}


# ---- 1 個体の測定（run.py と契約テストが同じ関数を使う）------------------------------------------------------

def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    """同じ seed から、自然な本体 22 と、（τ があれば）入れ替えた本体 42 と確認の本体 2 を測る。
    生の記録だけを返す（観測の量は計算しない）。"""
    plan = plan if plan is not None else plan_from(protocol)
    check_plan(plan)
    lo, hi = plan.swap_window
    labels = {b: labels_of(protocol, plan, seed, b) for b in BODIES}
    diverge = {b: first_label_divergence(labels["O"], labels[b]) for b in BODIES if b != "O"}
    before = {d - 1 for d in diverge.values() if d is not None}
    natural, recipient = {}, {}
    for b in BODIES:
        snap = before if b == "O" else ({diverge[b] - 1} if diverge[b] is not None else set())
        rec, clones = run_body(protocol, plan, seed, b, labels[b], snap, keep_clones=b == RECIPIENT)
        if b == RECIPIENT:
            recipient = clones
        natural[b] = rec | {"labels": [list(x) for x in labels[b]],
                            "rng": rng_name(seed, shuffle_index(b)) if b in SHUFFLES else None,
                            "first_divergence_from_O": diverge.get(b)}
    spikes = {b: natural[b]["spikes"] for b in BODIES}
    tau = find_swap_time(spikes, lo, hi)
    for b in BODIES:
        window_states = natural[b].pop("window_states")
        natural[b]["state_tau"] = window_states[tau] if tau is not None else None
    swapped: list[dict] = []
    controls: list[dict] = []
    if tau is None:
        recipient.clear()
        swap = {"tau_exists": False, "tau": None,
                "window_witness": window_witness(spikes, protocol["brain"]["sensory_units"], lo, hi),
                "events": no_tau_events()}
    else:
        base = recipient[tau]
        recipient.clear()
        for block in BLOCK_NAMES:
            for d in DONORS:
                swapped.append({"block": block, "family": FAMILY_OF[block], "donor": d,
                                "swap": {"tau": tau, "recipient": RECIPIENT, "blocks": [block], "donor": d}}
                               | run_swapped(plan, base, tau, natural[d]["state_tau"], (block,)))
        for name, donor in (("full_swap", "O"), ("null_swap", RECIPIENT)):
            controls.append({"name": name, "swap": {"tau": tau, "recipient": RECIPIENT, "blocks": list(BLOCK_NAMES), "donor": donor}}
                            | run_swapped(plan, base, tau, natural[donor]["state_tau"], BLOCK_NAMES))
        swap = {"tau_exists": True, "tau": tau, "window_witness": None, "events": None}
    return {"seed": seed, "plan": plan.as_dict(),
            "roles": {"receptors": role_receptors(protocol, seed), "units": role_units(protocol, seed)},
            "swap_window": [lo, hi], "swap": swap,
            "natural_bodies": natural, "swapped_bodies": swapped, "control_bodies": controls}
