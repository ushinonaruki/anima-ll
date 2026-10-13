"""実験 0022 の道具（確定した事前登録 v0.2 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 経験・刺激の列：0014〜0021 と同じ格子（乱数の流れの名前は protocol の stimulus.rng_shuffle）。ordered・shuffled の
    両方の本体を、それぞれ自然な個体 O・S として W の終わり（T）まで進める（protocol の stimulus.shuffled_runs_to）
- 8 つの腕（README §2）：O・S（自然な個体、ordered・shuffled の本体そのもの）、Y_O_from_S（O の複製、可塑性は S の発火）、
    Y_S_from_O（S の複製、可塑性は O の発火）、twin_O・twin_S（複製の確認）、Y_O_from_O・Y_S_from_S（自己 yoke の確認）。
    W の各 Pulse で pulse_order の順に 1 Pulse ずつ進める。複製は t0 の可塑性の更新の後に作り、状態は何も変えない
- yoke（README §2、protocol の yoke）：yoke の腕の Runtime に渡す接続の状態だけを YokedConnections で包み、Pulse の終わりの
    可塑性の更新に、Runtime が渡す自分の発火の集合ではなく、同じ Pulse の相手の自然な個体の発火の集合を渡す。
    発火の出来事と痕跡の更新の両方が相手の列で進む。痕跡の初めの値は、複製した基準の個体の t0 の値のまま（traces_initial）。
    重みの固定・伝達・Unit の状態は自分のまま。Runtime の本体・Unit・可塑性の規則・Birth State は変えない
- 記録（README §4）：全腕の W の全発火・感覚の出来事、60 Pulse ごとの全腕の接続の状態と Unit の状態、t0 の複製の全状態と
    次の Pulse に届く駆動、分岐の記録（t_OS・t_YO・t_YS）、T の全腕の状態
- 監査用の生記録（README §4）：O・S・Y_O_from_S・Y_S_from_O の Unit の力学のオブジェクトだけを AuditedDynamics で包み
    （Runtime・Unit の本体は変えない）、各 Pulse の Unit の判定の直前の activity を記録する。分岐の Pulse のものを残す
- 再構成（analyze.py と契約テストが使う）：可塑性の再生（切り詰めの監査・affine の係数つき）、発火の判定の再構成

複製・時間の進め方・来歴のログ・Receptor は 0012 の道具、刺激の列・再生の確認は 0015 の道具、接続の id は 0014 の道具を使う
（この実験専用に読み込み、乱数の流れの名前だけをこの実験の protocol のものにする）。
可塑性の 1 Pulse の更新は本体の実装（plasticity.balanced_pair_window）をそのまま呼ぶ。
README 付録 A の玩具（pre_registration_toy/）は、この道具に読み込まない・使わない。
"""

import dataclasses
import importlib.util
import math
from collections.abc import Collection, Iterable, Mapping
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
from anima_ll.domain.model.runtime_event import RuntimeEventType
from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PROTOCOL_PATH = HERE.relative_to(ROOT) / "protocol.yaml"
PROTOCOL = yaml.safe_load((ROOT / PROTOCOL_PATH).read_text(encoding="utf-8"))

# 実験の ID・乱数の流れの名前は protocol から読む（README §7.2）
EXPERIMENT = PROTOCOL["experiment"]
RNG_SHUFFLE = PROTOCOL["stimulus"]["rng_shuffle"]
# protocol の名前・式の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
INTERVENTION_RULE = "yoke_plasticity_input_to_partner_natural_individual"
INTERVENTION_AT = "experience_end"
SHUFFLED_RUNS_TO = "total_pulses"
CONDITIONS = ("ordered", "shuffled")
NATURAL = {"O": "ordered", "S": "shuffled"}     # 自然な個体 → 条件（その条件の本体そのもの）
# 各 Pulse で進める順（protocol の yoke.pulse_order）。自然な 2 個体を先に進める
ARMS = ("O", "S", "Y_O_from_S", "Y_S_from_O", "twin_O", "twin_S", "Y_O_from_O", "Y_S_from_S")
BASE = {"O": "O", "S": "S", "Y_O_from_S": "O", "Y_S_from_O": "S",
        "twin_O": "O", "twin_S": "S", "Y_O_from_O": "O", "Y_S_from_S": "S"}   # t0 の状態の出どころ
SOURCE = {"Y_O_from_S": "S", "Y_S_from_O": "O", "Y_O_from_O": "O", "Y_S_from_S": "S"}  # yoke の腕 → 可塑性の入力の個体
YOKED = tuple(a for a in ARMS if a in SOURCE)
AUDITED = ("O", "S", "Y_O_from_S", "Y_S_from_O")
PAIRS = {"YO": ("O", "Y_O_from_S"), "YS": ("S", "Y_S_from_O")}   # 主の観測の組（基準, yoke の腕）
NATURAL_PAIR = ("O", "S")
ROLES = ("A", "B", "C")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W14 = _load(f"world_0014_for_{EXPERIMENT}", ROOT / "experiments/0014_order_to_activity/world.py")
# 0015 の道具はこの実験専用に読み込み、乱数の流れの名前だけを protocol のものに替える
# （0015 の刺激の関数は、呼ばれたときにこのモジュールの RNG_SHUFFLE を読む）
W15 = _load(f"world_0015_for_{EXPERIMENT}", ROOT / "experiments/0015_history_difference_persistence/world.py")
W15.RNG_SHUFFLE = RNG_SHUFFLE

ExperimentLog = W14.ExperimentLog
clone = W14.clone
advance_to = W14.advance_to
connection_id = W14.connection_id
role_units = W15.role_units
role_receptors = W15.role_receptors
stimuli = W15.stimuli
first_divergence = W15.first_divergence
check_stimulus_counts = W15.check_stimulus_counts
replay_error = W15.replay_error
initial_weights = W15.initial_weights
weights = W15.weights
snapshot = W15.snapshot
unit_states = W15.unit_states
experience_end = W15.experience_end
total_pulses = W15.total_pulses
sample_every = W15.sample_every
plasticity = W15.plasticity


def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


def build(protocol: dict, condition: str, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    exp = protocol["experiment"]
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-{exp}-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=W15.receptors_for(protocol, condition, seed),
        run_metadata={"experiment": exp, "condition": condition,
                      "receptors": "ScheduledReceptor（experiments/0012_passive_world/world.py）"},
    )


def in_flight(app: Application) -> dict:
    """次の Pulse に届く駆動（Shared Brain State に置かれたもの）と、残っている Delta の数。複製の一致の確認に使う。"""
    state = app.pulse_runtime.brain_state
    return {"drives": sorted([[d.source_id, d.target_id, d.weight, d.created_pulse] for d in state.drives]),
            "deltas": len(state.deltas)}


# ---- yoke（README §2）---------------------------------------------------------------------------

class YokeError(RuntimeError):
    """yoke の契約（同じ Pulse の相手の発火を、ちょうど 1 回、可塑性にだけ渡す）が破れた。"""


class YokedConnections:
    """yoke の腕の Runtime に渡す接続の状態の包み（接続の状態のポート：weights・apply_activity・export_state）。

    - weights・export_state は包んだ本物の接続の状態をそのまま返す（重みの固定・伝達は自分の重み）
    - apply_activity（Pulse の終わりの可塑性の更新）では、Runtime が渡す自分の発火の集合を使わず、
      provide で渡された「同じ Pulse の相手の個体の発火の集合」で本物を更新する（出来事と痕跡の更新の両方が相手の列で進む。
      痕跡の値そのものは本物が持つ自分の値から進む）
    - 渡された集合は、その Pulse に 1 回だけ使う。Pulse 番号が一致しない・渡されていない・使われずに残ると YokeError
    """

    def __init__(self, inner, lifecycle) -> None:
        self.inner, self._lifecycle = inner, lifecycle
        self._provided: tuple[int, frozenset] | None = None

    def provide(self, pulse: PulseNumber, fired: Collection[ComponentId]) -> None:
        if self._provided is not None:
            raise YokeError(f"Pulse {self._provided[0]} の相手の発火が、まだ使われていない")
        if fired is None:
            raise YokeError(f"Pulse {pulse} の相手の発火がない（相手の個体をまだ進めていない）")
        self._provided = (pulse, frozenset(fired))

    def consumed(self) -> bool:
        return self._provided is None

    def weights(self):
        return self.inner.weights()

    def export_state(self):
        return self.inner.export_state()

    def apply_activity(self, fired: Collection[ComponentId], delta_time: float) -> None:
        if self._provided is None:
            raise YokeError(f"Pulse {self._lifecycle.pulse} の相手の発火が渡されていない")
        pulse, source = self._provided
        if pulse != self._lifecycle.pulse:
            raise YokeError(f"渡された相手の発火の Pulse（{pulse}）が、今の Pulse（{self._lifecycle.pulse}）と違う")
        self._provided = None
        self.inner.apply_activity(source, delta_time)


def make_yoked(app: Application) -> YokedConnections:
    """複製した腕の Runtime の接続の状態だけを包みに差し替える（app.connections は本物のまま：書き出し・読み込み用）。"""
    yoke = YokedConnections(app.connections, app.lifecycle)
    app.pulse_runtime._connections = yoke
    return yoke


# ---- 判定の直前の activity の監査 -------------------------------------------------------------------

class AuditedDynamics:
    """Unit の力学のオブジェクトの監査用の包み（実験の道具の中だけ。Runtime・Unit の本体は変えない）。

    advance は本物の advance をそのまま呼んで、その結果を返す（Unit の振る舞いは変わらない。twin との厳密一致で確かめる）。
    同時に、Unit が渡した実際の入力（状態・刺激・Δt）と、判定の直前の activity を記録する。判定の直前の activity は、
    閾値だけを無限大にした同じ実装の写しに同じ入力を渡して得る（同じ式・同じ順序で計算された、発火による 0 へのリセットの前の値）。
    """

    def __init__(self, inner, sink: dict, unit_id: ComponentId, lifecycle) -> None:
        self.inner, self._sink, self._unit_id, self._lifecycle = inner, sink, unit_id, lifecycle
        self._probe = dataclasses.replace(inner, threshold=math.inf)

    def advance(self, state, stimulus: float, delta_time: float):
        probe_state, probe_fired = self._probe.advance(state, stimulus, delta_time)
        new_state, firing = self.inner.advance(state, stimulus, delta_time)
        self._sink[self._unit_id] = {
            "pulse": self._lifecycle.pulse, "activity_in": state.activity, "adaptation_in": state.adaptation,
            "stimulus": stimulus, "delta_time": delta_time, "activity_pre": probe_state.activity,
            "probe_fired": probe_fired is not None, "fired": firing is not None,
            "activity_out": new_state.activity, "adaptation_out": new_state.adaptation}
        return new_state, firing

    def describe(self):
        return self.inner.describe()

    def __getattr__(self, name):
        return getattr(self.inner, name)


def make_audited(app: Application) -> dict:
    """腕の各 Unit の力学を AuditedDynamics で包み、その Pulse の監査の記録を入れる dict（Unit → 記録）を返す。"""
    sink: dict = {}
    for unit in app.units.all():
        unit._dynamics = AuditedDynamics(unit._dynamics, sink, unit.unit_id, app.lifecycle)
    return sink


# ---- 8 つの腕を 1 Pulse ずつ並べて進める -------------------------------------------------------------

class _EventReader:
    """来歴ログから、前に読んだところより後の発火・感覚の出来事だけを読む。"""

    def __init__(self, log: ExperimentLog) -> None:
        self.log, self.pos = log, len(log.events)

    def new(self) -> tuple[list[list], list[list]]:
        events = self.log.events[self.pos:]
        self.pos = len(self.log.events)
        act = [[e.pulse, e.data["unit_id"]] for e in events if e.type == RuntimeEventType.ACTIVITY]
        sen = [[e.pulse, e.data["receptor_id"]] for e in events if e.type == RuntimeEventType.SENSORY]
        return act, sen


def _divergence_record(t: int, units: list[str], arms: Iterable[str], hist: Mapping[str, list],
                       last: Mapping[str, list], now: Mapping[str, list], audit_now: Mapping[str, dict]) -> dict:
    arms = list(arms)
    return {"pulse": t, "units": units, "arms": arms,
            "before": {"t-2": {a: hist[a][0] for a in arms} if len(hist[arms[0]]) == 2 else None,
                       "t-1": {a: hist[a][-1] for a in arms}},
            "spikes": {"t-1": {a: list(last[a]) for a in arms}, "t": {a: list(now[a]) for a in arms}},
            "audit": {a: audit_now[a] for a in arms}}


def run_arms(arms: Mapping[str, tuple[Application, ExperimentLog]], yokes: Mapping[str, YokedConnections],
             start: PulseNumber, end: PulseNumber, every: int, audits: Mapping[str, dict]) -> dict:
    """8 つの腕を start の終わりから end まで、ARMS の順に 1 Pulse ずつ並べて進める。どの腕も start まで進んでいること。

    yokes：yoke の腕の名前 → 包み。各 Pulse で、相手の自然な個体（SOURCE）を進めて得た発火の集合を、その Pulse の前に包みへ渡す。
    audits：監査する腕（AUDITED）の名前 → make_audited の dict。各 Pulse の後に読み、分岐の Pulse のものを分岐の記録に残す。

    返す値（すべて生の記録）：
      spikes   {腕: [[Pulse, Unit]]}（start ＋ 1〜end）
      sensory  {腕: [[Pulse, Receptor]]}（start ＋ 1〜end。入力なしなら空）
      samples  {腕: {Pulse: {units, connections}}}（start と、start から every ごと、end）
      t_OS     None か {pulse, units, arms, before: {t−2, t−1: {腕: 状態}}, spikes: {t−1, t: {腕: [...]}}, audit: {腕: {Unit: 記録}},
                        after: {t, t+1: {腕: 状態} か None}, spikes_after: {t+1: {腕: [...]} か None}}
                        （腕は O・S・Y_O_from_S・Y_S_from_O。after は yoke の腕と基準の t_OS ＋ 1 までの一致の確認のため）
      t_YO     同じ形（O・Y_O_from_S。after なし）
      t_YS     同じ形（S・Y_S_from_O。after なし）
    """
    if tuple(arms) != ARMS:
        raise ValueError(f"腕の並びが {ARMS} ではない（{tuple(arms)}）")
    if set(yokes) != set(YOKED):
        raise ValueError(f"yoke する腕が {YOKED} ではない（{tuple(yokes)}）")
    if set(audits) != set(AUDITED):
        raise ValueError(f"監査する腕が {AUDITED} ではない（{tuple(audits)}）")
    for name, (app, _) in arms.items():
        if app.lifecycle.pulse != start:
            raise ValueError(f"{name} は Pulse {start} まで進んでいること（今 {app.lifecycle.pulse}）")
    readers = {name: _EventReader(log) for name, (_, log) in arms.items()}
    spikes: dict[str, list] = {name: [] for name in arms}
    sensory: dict[str, list] = {name: [] for name in arms}
    samples: dict[str, dict] = {name: {} for name in arms}
    hist = {name: [snapshot(arms[name][0])] for name in AUDITED}     # 直前 2 Pulse の終わりの状態
    last = {name: [] for name in AUDITED}
    found: dict[str, dict | None] = {"t_OS": None, "t_YO": None, "t_YS": None}
    watch = {"t_OS": NATURAL_PAIR, "t_YO": PAIRS["YO"], "t_YS": PAIRS["YS"]}
    record_arms = {"t_OS": AUDITED, "t_YO": PAIRS["YO"], "t_YS": PAIRS["YS"]}

    def sample(t: int) -> None:
        for name, (app, _) in arms.items():
            samples[name][str(t)] = snapshot(app)

    sample(start)
    for t in range(start + 1, end + 1):
        now: dict[str, list] = {}
        audit_now: dict[str, dict] = {}
        fired: dict[str, frozenset | None] = {"O": None, "S": None}
        for name, (app, _) in arms.items():
            if name in yokes:
                yokes[name].provide(t, fired[SOURCE[name]])
            advance_to(app, t)
            if name in yokes and not yokes[name].consumed():
                raise YokeError(f"{name}：Pulse {t} の相手の発火が、可塑性の更新に使われなかった")
            if name in audits:
                got = audits[name]
                if set(got) != {x.unit_id for x in app.units.all()} or any(r["pulse"] != t for r in got.values()):
                    raise ValueError(f"{name}：Pulse {t} の監査の記録が全 Unit でそろっていない")
                audit_now[name] = {u: dict(r) for u, r in got.items()}
            act, sen = readers[name].new()
            now[name] = act
            spikes[name] += act
            sensory[name] += sen
            if name in fired:
                fired[name] = frozenset(u for _, u in act)
        sets = {n: {u for _, u in now[n]} for n in AUDITED}
        # t_OS の直後の状態（yoke の腕と基準が t_OS ＋ 1 まで同じことの確認のため）
        rec = found["t_OS"]
        if rec is not None and rec["after"]["t+1"] is None and t == rec["pulse"] + 1:
            rec["after"]["t+1"] = {a: snapshot(arms[a][0]) for a in AUDITED}
            rec["spikes_after"] = {"t+1": {a: list(now[a]) for a in AUDITED}}
        for key, (a, b) in watch.items():
            if found[key] is None and sets[a] != sets[b]:
                found[key] = _divergence_record(t, sorted(sets[a] ^ sets[b]), record_arms[key], hist, last, now, audit_now)
                if key == "t_OS":
                    found[key]["after"] = {"t": {x: snapshot(arms[x][0]) for x in AUDITED}, "t+1": None}
                    found[key]["spikes_after"] = None
        for name in AUDITED:
            hist[name] = (hist[name] + [snapshot(arms[name][0])])[-2:]
            last[name] = now[name]
        if (t - start) % every == 0 or t == end:
            sample(t)
    return {"spikes": spikes, "sensory": sensory, "samples": samples} | found


# ---- 再構成（判定ではない。analyze.py と契約テストが使う） ---------------------------------------------

def unit_of(cid: str) -> tuple[str, str]:
    """"s1.main->s2" → ("s1", "s2")。"""
    src, dst = cid.split("->")
    return src.split(".")[0], dst


def fired_by_pulse(spikes: Iterable[list]) -> dict[int, set]:
    out: dict[int, set] = {}
    for p, u in spikes:
        out.setdefault(p, set()).add(u)
    return out


def replay(state0: Mapping[str, float], cid: str, fired: Mapping[int, set], start: PulseNumber, end: PulseNumber,
           spec, dt: float, record: Collection[int] = ()) -> dict:
    """1 本の接続を start の終わりの状態（重み・痕跡）から end まで、与えた発火（Pulse → Unit の集合）で、
    本体の 1 Pulse の更新 balanced_pair_window を呼んで進める。

    返す値：end の状態、record に入れた Pulse の終わりの状態、affine の係数 S・B（w' ＝ s·w ＋ c の合成）、
      clipped（切り詰めの min・max が値を変えた Pulse の一覧。README §6 の「切り詰めなし」の監査）
    """
    src, dst = unit_of(cid)
    st = PlasticState(weight=state0["weight"], pre_trace=state0["pre_trace"], post_trace=state0["post_trace"])
    S, B, clipped, at = 1.0, 0.0, [], {}
    ratio = spec.amplitude / spec.w_max
    want = set(record)
    for p in range(start + 1, end + 1):
        f = fired.get(p, ())
        pre_fired, post_fired = src in f, dst in f
        x, y, w = st.pre_trace, st.post_trace, st.weight
        s = 1.0 - ratio * (x * post_fired + y * pre_fired)
        c = spec.amplitude * x * post_fired
        S, B = s * S, s * B + c
        raw = w + (spec.amplitude * x * (spec.w_max - w) / spec.w_max if post_fired else 0.0) \
                - (spec.amplitude * y * w / spec.w_max if pre_fired else 0.0)
        st = balanced_pair_window(st, pre_fired=pre_fired, post_fired=post_fired, delta_time=dt, spec=spec)
        if st.weight != raw:
            clipped.append(p)
        if p in want:
            at[p] = {"weight": st.weight, "pre_trace": st.pre_trace, "post_trace": st.post_trace}
    if start in want:
        at[start] = dict(state0)
    return {"end": {"weight": st.weight, "pre_trace": st.pre_trace, "post_trace": st.post_trace},
            "at": at, "S": S, "B": B, "clipped": clipped}


def birth_replay_weights(protocol: dict, activity: Iterable[list], end: PulseNumber) -> dict[str, float]:
    """出生時の状態（設計図の重み・痕跡 0）から、本体の更新で end の終わりまで進めた 6 本の重み。
    t0 ＋ 1 に届く駆動の重み w(t0 − 1) を、記録した発火から求めるのに使う（O は ordered、S は shuffled の発火）。"""
    spec = plasticity(protocol)
    dt = protocol["timeline"]["pulse_interval_seconds"]
    fired = fired_by_pulse(a for a in activity if a[0] <= end)
    out = {}
    for cid, w0 in initial_weights(protocol).items():
        out[cid] = replay({"weight": w0, "pre_trace": 0.0, "post_trace": 0.0}, cid, fired, 0, end, spec, dt)["end"]["weight"]
    return out


def reconstruct_firing(units_tm1: Mapping[str, Mapping], weights_tm2: Mapping[str, float],
                       spikes_tm1: Iterable[list], dt: float) -> dict[str, dict]:
    """Pulse t の各 Unit の発火の判定を、t − 1 の終わりの Unit の状態、t − 2 の終わりの重み（t − 1 の伝達に使う重み）、
    t − 1 の発火から再構成する（runtime の順序：t − 1 の冒頭で重みを固定 → t − 1 の発火を駆動にして t に届ける）。
    返す値：{Unit: {activity_pre, threshold_eff, drive: {送り手: 駆動}, fires}}（不応期 0 が前提）
    """
    fired = {u for _, u in spikes_tm1}
    out = {}
    for uid, s in units_tm1.items():
        d = s["dynamics"]
        drive = {src: w for cid, w in weights_tm2.items()
                 for src, dst in [unit_of(cid)] if dst == uid and src in fired}
        act = s["activity"] * d["decay_per_second"] ** dt + sum(drive.values()) + d["intrinsic_drive_per_second"] * dt
        adapt = s["adaptation"]
        if adapt and d["adaptation_tau_seconds"] > 0:
            adapt *= math.exp(-dt / d["adaptation_tau_seconds"])
        thr = d["threshold"] + adapt
        out[uid] = {"activity_pre": act, "threshold_eff": thr, "drive": drive,
                    "fires": s["refractory_remaining"] <= 0 and act >= thr}
    return out


# ---- 複製と 8 腕の組み立て（measure_seed と契約テストが同じ関数を使う） -----------------------------------

def fork_arms(O: tuple[Application, ExperimentLog], S: tuple[Application, ExperimentLog]) -> dict:
    """t0 の終わりの自然な 2 個体から、残りの 6 腕を複製で作る（状態は何も変えない）。腕の並びは ARMS。"""
    natural = {"O": O, "S": S}
    arms = {}
    for name in ARMS:
        arms[name] = natural[name] if name in natural else clone(*natural[BASE[name]])
    return arms


def wrap_arms(arms: Mapping[str, tuple[Application, ExperimentLog]]) -> tuple[dict, dict]:
    """yoke の腕を包み、監査する腕の力学を包む（複製の後。確認の twin・自己 yoke の力学は包まない）。"""
    yokes = {name: make_yoked(arms[name][0]) for name in YOKED}
    audits = {name: make_audited(arms[name][0]) for name in AUDITED}
    return yokes, audits


# ---- 1 個体の測定（run.py と通しの確認が同じ関数を使う） ---------------------------------------------

def measure_seed(protocol: dict, seed: int) -> dict:
    end, total, every = experience_end(protocol), total_pulses(protocol), sample_every(protocol)
    if (protocol["intervention"]["at"] != INTERVENTION_AT or protocol["stimulus"]["shuffled_runs_to"] != SHUFFLED_RUNS_TO
            or protocol["intervention"]["rule"] != INTERVENTION_RULE):
        raise ValueError("介入の時点・規則・shuffled を進める終わりの式が道具と違う")
    units = role_units(protocol, seed)
    diverge = first_divergence(protocol, seed)
    apps, logs, out = {}, {}, {}
    for c in CONDITIONS:
        logs[c] = ExperimentLog()
        apps[c] = build(protocol, c, seed, logs[c])
        out[c] = {"birth": unit_states(apps[c]), "before_divergence": None}
    for t in sorted({end} | ({diverge - 1} if diverge is not None else set())):
        for c in CONDITIONS:
            advance_to(apps[c], t)
            if diverge is not None and t == diverge - 1:
                out[c]["before_divergence"] = snapshot(apps[c])
    for c in CONDITIONS:                       # 経験の終わり（t0）の記録。O・S はこのあと本体のまま W を進む
        out[c] |= {"connections_12000": apps[c].connections.export_state(), "units_12000": unit_states(apps[c]),
                   "activity": logs[c].activity(), "sensory": logs[c].sensory()}
    # t0 の終わりで分ける。O・S は ordered・shuffled の本体そのもの
    arms = fork_arms((apps["ordered"], logs["ordered"]), (apps["shuffled"], logs["shuffled"]))
    fork = {name: snapshot(app) for name, (app, _) in arms.items()}
    fork_in_flight = {name: in_flight(app) for name, (app, _) in arms.items()}
    yokes, audits = wrap_arms(arms)
    res = run_arms(arms, yokes, end, total, every, audits)
    return {"seed": seed, "first_divergence_history": diverge,
            "roles": {"receptors": role_receptors(protocol, seed), "units": units},
            "conditions": out, "fork": fork, "fork_in_flight": fork_in_flight, "arms": res,
            "endpoints": {name: snapshot(app) for name, (app, _) in arms.items()}}
