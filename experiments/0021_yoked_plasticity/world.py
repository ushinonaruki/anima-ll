"""実験 0021 の道具（事前登録 v0.1 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 経験・刺激の列・介入：0020 と同じ（乱数の流れの名前は protocol の stimulus.rng_shuffle）
- 5 つの腕（README §2）：C（ordered の本体）・I（C の複製、4 本を移植）・Y（I の複製、yoked）・twin（C の複製）・
    Y0（C の複製、yoked）。W の各 Pulse で pulse_order（C → I → Y → twin → Y0）の順に 1 Pulse ずつ進める
- yoke（README §2、protocol の yoke）：Y・Y0 の Runtime に渡す接続の状態だけを YokedConnections で包み、
    Pulse の終わりの可塑性の更新に、Runtime が渡す自分の発火の集合ではなく、同じ Pulse の C の発火の集合を渡す
    （発火の出来事と痕跡の両方が C の列で進む）。重みの固定・伝達・Unit の状態は自分のまま。Runtime の本体は変えない
- 記録（README §4）：全腕の W の全発火・感覚の出来事、60 Pulse ごとの全腕の接続の状態と Unit の状態、
    t1（C・I・Y）と t2（I・Y）の直前 2 Pulse の全状態と t − 1・t の発火、T の全腕の状態
- 再構成（analyze.py と契約テストが使う）：affine の係数、可塑性の再生（切り詰めの監査つき）、発火の判定の再構成

複製・時間の進め方・来歴のログ・Receptor は 0012 の道具、刺激の列・再生の確認は 0015 の道具、
接続の id は 0014 の道具を使う（この実験専用に読み込み、乱数の流れの名前だけを 0021 の protocol のものにする）。
可塑性の 1 Pulse の更新は本体の実装（plasticity.balanced_pair_window）をそのまま呼ぶ。
"""

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

# 実験の ID・乱数の流れの名前は protocol から読む（README §7.1。0020 を参照したままにしない）
EXPERIMENT = PROTOCOL["experiment"]
RNG_SHUFFLE = PROTOCOL["stimulus"]["rng_shuffle"]
# protocol の名前・式の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
INTERVENTION_RULE = "transplant_ab_ac_target_weights_from_shuffled"
INTERVENTION_AT = "experience_end"
ARMS = ("C", "I", "Y", "twin", "Y0")             # 各 Pulse で進める順（protocol の yoke.pulse_order）
YOKED = ("Y", "Y0")                               # 可塑性の更新に C の発火を使う腕
SOURCE = "C"
CONDITIONS = ("ordered", "shuffled")
TARGETS = ("AB", "AC", "BA", "CA")
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
four_ids = W14.four_ids
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


# ---- 介入 ----------------------------------------------------------------------------------------

def target_weights(connections: Mapping[str, Mapping], units: Mapping[str, ComponentId]) -> dict[str, float]:
    ids = four_ids(units)
    return {k: connections[ids[k]]["weight"] for k in TARGETS}


def transplant(app: Application, units: Mapping[str, ComponentId], donor: Mapping[str, float]) -> None:
    """複製の上でだけ使う：4 本の weight だけを置き換える。痕跡・他の接続・Unit の状態はそのまま。"""
    ids = four_ids(units)
    state = app.connections.export_state()
    for k in TARGETS:
        state[ids[k]]["weight"] = donor[k]
    app.connections.import_state(state)


# ---- yoke（README §2）---------------------------------------------------------------------------

class YokeError(RuntimeError):
    """yoke の契約（同じ Pulse の C の発火を、ちょうど 1 回、可塑性にだけ渡す）が破れた。"""


class YokedConnections:
    """Y・Y0 の Runtime に渡す接続の状態の包み（接続の状態のポート：weights・apply_activity・export_state）。

    - weights・export_state は包んだ本物の接続の状態をそのまま返す（重みの固定・伝達は自分の重み）
    - apply_activity（Pulse の終わりの可塑性の更新）では、Runtime が渡す自分の発火の集合を使わず、
      provide で渡された「同じ Pulse の C の発火の集合」で本物を更新する（出来事と痕跡の両方が C の列で進む）
    - 渡された集合は、その Pulse に 1 回だけ使う。Pulse 番号が一致しない・渡されていない・使われずに残ると YokeError
    """

    def __init__(self, inner, lifecycle) -> None:
        self.inner, self._lifecycle = inner, lifecycle
        self._provided: tuple[int, frozenset] | None = None

    def provide(self, pulse: PulseNumber, fired: Collection[ComponentId]) -> None:
        if self._provided is not None:
            raise YokeError(f"Pulse {self._provided[0]} の C の発火が、まだ使われていない")
        self._provided = (pulse, frozenset(fired))

    def consumed(self) -> bool:
        return self._provided is None

    def weights(self):
        return self.inner.weights()

    def export_state(self):
        return self.inner.export_state()

    def apply_activity(self, fired: Collection[ComponentId], delta_time: float) -> None:
        if self._provided is None:
            raise YokeError(f"Pulse {self._lifecycle.pulse} の C の発火が渡されていない")
        pulse, source = self._provided
        if pulse != self._lifecycle.pulse:
            raise YokeError(f"渡された C の発火の Pulse（{pulse}）が、今の Pulse（{self._lifecycle.pulse}）と違う")
        self._provided = None
        self.inner.apply_activity(source, delta_time)


def make_yoked(app: Application) -> YokedConnections:
    """複製した腕の Runtime の接続の状態だけを包みに差し替える（app.connections は本物のまま：書き出し・読み込み用）。"""
    yoke = YokedConnections(app.connections, app.lifecycle)
    app.pulse_runtime._connections = yoke
    return yoke


# ---- 5 つの腕を 1 Pulse ずつ並べて進める -------------------------------------------------------------

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
                       last: Mapping[str, list], now: Mapping[str, list]) -> dict:
    arms = list(arms)
    return {"pulse": t, "units": units,
            "before": {"t-2": {a: hist[a][0] for a in arms} if len(hist[arms[0]]) == 2 else None,
                       "t-1": {a: hist[a][-1] for a in arms}},
            "spikes": {"t-1": {a: list(last[a]) for a in arms}, "t": {a: list(now[a]) for a in arms}}}


def run_arms(arms: Mapping[str, tuple[Application, ExperimentLog]], yokes: Mapping[str, YokedConnections],
             start: PulseNumber, end: PulseNumber, every: int) -> dict:
    """5 つの腕を start の終わりから end まで、ARMS の順に 1 Pulse ずつ並べて進める。どの腕も start まで進んでいること。

    yokes：yoked の腕の名前 → 包み。各 Pulse で、SOURCE（C）を進めて得た発火の集合を、その Pulse の前に包みへ渡す。

    返す値（すべて生の記録）：
      spikes   {腕: [[Pulse, Unit]]}（start ＋ 1〜end）
      sensory  {腕: [[Pulse, Receptor]]}（start ＋ 1〜end。入力なしなら空）
      samples  {腕: {Pulse: {connections, units}}}（start と、start から every ごと、end）
      t1       None か {pulse, units, before: {t−2, t−1: {腕: {units, connections}}}, spikes: {t−1, t: {腕: [...]}}}（C・I・Y）
      t2       同じ形（I・Y）
    """
    if tuple(arms) != ARMS:
        raise ValueError(f"腕の並びが {ARMS} ではない（{tuple(arms)}）")
    if set(yokes) != set(YOKED):
        raise ValueError(f"yoke する腕が {YOKED} ではない（{tuple(yokes)}）")
    for name, (app, _) in arms.items():
        if app.lifecycle.pulse != start:
            raise ValueError(f"{name} は Pulse {start} まで進んでいること（今 {app.lifecycle.pulse}）")
    readers = {name: _EventReader(log) for name, (_, log) in arms.items()}
    spikes: dict[str, list] = {name: [] for name in arms}
    sensory: dict[str, list] = {name: [] for name in arms}
    samples: dict[str, dict] = {name: {} for name in arms}
    watched = ("C", "I", "Y")
    hist = {name: [snapshot(arms[name][0])] for name in watched}     # 直前 2 Pulse の終わりの状態
    last = {name: [] for name in watched}
    t1 = t2 = None

    def sample(t: int) -> None:
        for name, (app, _) in arms.items():
            samples[name][str(t)] = snapshot(app)

    sample(start)
    for t in range(start + 1, end + 1):
        now: dict[str, list] = {}
        fired_source: frozenset | None = None
        for name, (app, _) in arms.items():
            if name in yokes:
                yokes[name].provide(t, fired_source)
            advance_to(app, t)
            if name in yokes and not yokes[name].consumed():
                raise YokeError(f"{name}：Pulse {t} の C の発火が、可塑性の更新に使われなかった")
            act, sen = readers[name].new()
            now[name] = act
            spikes[name] += act
            sensory[name] += sen
            if name == SOURCE:
                fired_source = frozenset(u for _, u in act)
        sets = {n: {u for _, u in now[n]} for n in watched}
        if t1 is None and sets["C"] != sets["I"]:
            t1 = _divergence_record(t, sorted(sets["C"] ^ sets["I"]), ("C", "I", "Y"), hist, last, now)
        if t2 is None and sets["I"] != sets["Y"]:
            t2 = _divergence_record(t, sorted(sets["I"] ^ sets["Y"]), ("I", "Y"), hist, last, now)
        for name in watched:
            hist[name] = (hist[name] + [snapshot(arms[name][0])])[-2:]
            last[name] = now[name]
        if (t - start) % every == 0 or t == end:
            sample(t)
    return {"spikes": spikes, "sensory": sensory, "samples": samples, "t1": t1, "t2": t2}


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
    介入の前の重み w(t0 − 1)（t0 ＋ 1 に届く駆動の重み）を、記録した発火から求めるのに使う。"""
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
    返す値：{Unit: {activity_pre, threshold_eff, drive: {送り手: 駆動}, fires}}（不応期 0 が前提。README §3）
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


# ---- 1 個体の測定（run.py と通しの確認が同じ関数を使う） ---------------------------------------------

def measure_seed(protocol: dict, seed: int) -> dict:
    end, total, every = experience_end(protocol), total_pulses(protocol), sample_every(protocol)
    if protocol["intervention"]["at"] != INTERVENTION_AT or protocol["stimulus"]["shuffled_runs_to"] != INTERVENTION_AT:
        raise ValueError("介入の時点・shuffled を進める終わりの式が道具と違う")
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
    for c in CONDITIONS:                       # shuffled は 12000 まで（donor の値を取るためだけ）
        out[c] |= {"connections_12000": apps[c].connections.export_state(), "units_12000": unit_states(apps[c]),
                   "activity": logs[c].activity(), "sensory": logs[c].sensory()}
    # t0 の終わりで分ける。C は ordered の本体そのもの
    C, C_log = apps["ordered"], logs["ordered"]
    I, I_log = clone(C, C_log)
    transplant(I, units, target_weights(out["shuffled"]["connections_12000"], units))
    Y, Y_log = clone(I, I_log)
    twin, twin_log = clone(C, C_log)
    Y0, Y0_log = clone(C, C_log)
    arms = {"C": (C, C_log), "I": (I, I_log), "Y": (Y, Y_log), "twin": (twin, twin_log), "Y0": (Y0, Y0_log)}
    fork = {name: snapshot(app) for name, (app, _) in arms.items()}
    yokes = {name: make_yoked(arms[name][0]) for name in YOKED}
    res = run_arms(arms, yokes, end, total, every)
    return {"seed": seed, "first_divergence_history": diverge,
            "roles": {"receptors": role_receptors(protocol, seed), "units": units},
            "conditions": out, "fork": fork, "arms": res,
            "endpoints": {name: snapshot(app) for name, (app, _) in arms.items()}}
