"""探索 0020 の道具（探索の設計 v0.1 に従う。判定を置かない。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 経験・刺激の列：0015 v0.2 と同じ（乱数の流れの名前だけ "0020-shuffle:<seed>"）
- 介入（README §2）：Pulse 12000 の処理（可塑性の更新まで）の終わりに、ordered の本体を複製して介入腕にし、
    介入腕の w(A→B)・w(A→C)・w(B→A)・w(C→A) だけを shuffled の本体の 12000 の値に置き換える。
    control は ordered の本体そのもの。両腕を 12001〜24000 無入力で、1 Pulse ずつ並べて進める
- 記録（README §4）：両腕の全発火の列、各 Unit の閾値までの余裕の最小、60 Pulse ごとの標本、
    最初の分岐の Pulse とその直前 2 Pulse の両腕の全状態
- 再構成（analyze.py と契約テストが使う）：各腕の自分の発火の列からの affine の係数 S・B、強める・弱めるの内訳、
    最初の分岐の Pulse での発火の判定の再構成

複製・時間の進め方・来歴のログ・Receptor は 0012 の道具、刺激の列・再生の確認は 0015 の道具、
接続の id は 0014 の道具を使う。可塑性の 1 Pulse の更新は本体の実装（plasticity.balanced_pair_window）をそのまま呼ぶ。
"""

import importlib.util
import math
from collections.abc import Iterable, Mapping
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

# protocol.yaml の名前・式の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
RNG_SHUFFLE = "0020-shuffle:{seed}"
INTERVENTION_RULE = "transplant_ab_ac_target_weights_from_shuffled"
INTERVENTION_AT = "experience_end"
ARMS = ("control", "intervention")
CONDITIONS = ("ordered", "shuffled")
TARGETS = ("AB", "AC", "BA", "CA")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W14 = _load("world_0014_for_0020", ROOT / "experiments/0014_order_to_activity/world.py")
# 0015 の道具はこの探索専用に読み込み、乱数の流れの名前だけを 0020 のものに替える
# （0015 の刺激の関数は、呼ばれたときにこのモジュールの RNG_SHUFFLE を読む）
W15 = _load("world_0015_for_0020", ROOT / "experiments/0015_history_difference_persistence/world.py")
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
weights = W15.weights
w_contrast = W15.w_contrast
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
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-0020-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=W15.receptors_for(protocol, condition, seed),
        run_metadata={"experiment": "0020", "condition": condition,
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


# ---- 2 腕を 1 Pulse ずつ並べて進める ---------------------------------------------------------------

class _SpikeReader:
    """来歴ログから、前に読んだところより後の発火だけを読む（ログを毎 Pulse すべて読み直さない）。"""

    def __init__(self, log: ExperimentLog) -> None:
        self.log, self.pos = log, len(log.events)

    def new(self) -> list[list]:
        events = self.log.events[self.pos:]
        self.pos = len(self.log.events)
        return [[e.pulse, e.data["unit_id"]] for e in events if e.type == RuntimeEventType.ACTIVITY]


def run_arms(arms: Mapping[str, tuple[Application, ExperimentLog]], start: PulseNumber, end: PulseNumber,
             every: int, units: Mapping[str, ComponentId]) -> dict:
    """2 腕（control・intervention）を start の終わりから end まで、1 Pulse ずつ並べて進める。どちらも start まで進んでいること。

    返す値（すべて生の記録）：
      spikes         {腕: [[Pulse, Unit]]}（start ＋ 1〜end）
      min_margin     {腕: {Unit: [余裕の最小, その Pulse]}}（発火しなかった Pulse での θ ＋ adaptation − activity）
      samples        {腕: {Pulse: {targets, units}}}（start と、start から every ごと、end）
      divergence     None（列が一度も違わない）か {pulse, units, before: {t−2, t−1: {腕: {units, connections}}}, spikes: {t−1, t: {腕: [...]}}}
    """
    for name, (app, _) in arms.items():
        if app.lifecycle.pulse != start:
            raise ValueError(f"{name} は Pulse {start} まで進んでいること（今 {app.lifecycle.pulse}）")
    readers = {name: _SpikeReader(log) for name, (_, log) in arms.items()}
    spikes: dict[str, list] = {name: [] for name in arms}
    margin: dict[str, dict] = {name: {} for name in arms}
    samples: dict[str, dict] = {name: {} for name in arms}
    hist = {name: [snapshot(app)] for name, (app, _) in arms.items()}   # 直前 2 Pulse の終わりの状態
    last_spikes = {name: [] for name in arms}
    divergence = None

    def sample(t: int) -> None:
        for name, (app, _) in arms.items():
            st = app.connections.export_state()
            samples[name][str(t)] = {"targets": target_weights(st, units), "units": unit_states(app)}

    sample(start)
    for t in range(start + 1, end + 1):
        now = {}
        for name, (app, _) in arms.items():
            advance_to(app, t)
            now[name] = readers[name].new()
            spikes[name] += now[name]
            fired = {u for _, u in now[name]}
            for uid, s in unit_states(app).items():
                if uid in fired:
                    continue
                d = s["dynamics"]
                m = d["threshold"] + s["adaptation"] - s["activity"]
                if uid not in margin[name] or m < margin[name][uid][0]:
                    margin[name][uid] = [m, t]
        if divergence is None and sorted(map(tuple, now["control"])) != sorted(map(tuple, now["intervention"])):
            c, i = ({u for _, u in now[n]} for n in ("control", "intervention"))
            divergence = {"pulse": t, "units": sorted(c ^ i),
                          "before": {"t-2": {n: hist[n][0] for n in arms} if len(hist["control"]) == 2 else None,
                                     "t-1": {n: hist[n][-1] for n in arms}},
                          "spikes": {"t-1": dict(last_spikes), "t": dict(now)}}
        for name, (app, _) in arms.items():
            hist[name] = (hist[name] + [snapshot(app)])[-2:]
        last_spikes = now
        if (t - start) % every == 0 or t == end:
            sample(t)
    return {"spikes": spikes, "min_margin": margin, "samples": samples, "divergence": divergence}


# ---- 再構成（判定ではない。analyze.py と契約テストが使う） ---------------------------------------------

def affine(state0: Mapping[str, float], pre_spikes: Iterable[int], post_spikes: Iterable[int],
           start: PulseNumber, end: PulseNumber, spec, dt: float) -> dict:
    """1 本の接続を start の終わりの状態（重み・痕跡）から end まで、与えた発火の列で進める（README §3）。

    規則の 1 Pulse の更新は w について 1 次式 w' ＝ s·w ＋ c なので、合成は R(w₀) ＝ S·w₀ ＋ B。
    返す値：S、log_S（S を対数で足し上げたもの。丸め・アンダーフローの監査用）、B、
      w_end（state0 の重みから本体の実装 balanced_pair_window で進めた重み）、pot・dep（その道筋での強める・弱めるの合計）、
      n_factors_lt_1（s ＜ 1 だった Pulse の数）
    """
    pre, post = set(pre_spikes), set(post_spikes)
    st = PlasticState(weight=state0["weight"], pre_trace=state0["pre_trace"], post_trace=state0["post_trace"])
    S, log_S, B, pot, dep, n = 1.0, 0.0, 0.0, 0.0, 0.0, 0
    ratio = spec.amplitude / spec.w_max
    for p in range(start + 1, end + 1):
        post_fired, pre_fired = p in post, p in pre
        x, y, w = st.pre_trace, st.post_trace, st.weight
        s = 1.0 - ratio * (x * post_fired + y * pre_fired)
        c = spec.amplitude * x * post_fired
        S, B = s * S, s * B + c
        if s < 1.0:
            log_S += math.log(s)
            n += 1
        pot += spec.amplitude * x * (spec.w_max - w) / spec.w_max if post_fired else 0.0
        dep += spec.amplitude * y * w / spec.w_max if pre_fired else 0.0
        st = balanced_pair_window(st, pre_fired=pre_fired, post_fired=post_fired, delta_time=dt, spec=spec)
    return {"S": S, "log_S": log_S, "B": B, "w_end": st.weight, "pot": pot, "dep": dep, "n_factors_lt_1": n}


def unit_of(cid: str) -> tuple[str, str]:
    """"s1.main->s2" → ("s1", "s2")。"""
    src, dst = cid.split("->")
    return src.split(".")[0], dst


def reconstruct_firing(units_tm1: Mapping[str, Mapping], conns_tm2: Mapping[str, Mapping],
                       spikes_tm1: Iterable[list], dt: float) -> dict[str, dict]:
    """Pulse t の各 Unit の発火の判定を、t − 1 の終わりの Unit の状態、t − 2 の終わりの重み（t − 1 の伝達に使う重み）、
    t − 1 の発火から再構成する（README §4。runtime の順序：t − 1 の冒頭で重みを固定 → t − 1 の発火を駆動にして t に届ける）。
    返す値：{Unit: {activity_pre, threshold_eff, drive: {送り手: 駆動}, fires}}
    """
    fired = {u for _, u in spikes_tm1}
    out = {}
    for uid, s in units_tm1.items():
        d = s["dynamics"]
        drive = {src: c["weight"] for cid, c in conns_tm2.items()
                 for src, dst in [unit_of(cid)] if dst == uid and src in fired}
        act = s["activity"] * d["decay_per_second"] ** dt + sum(drive.values()) + d["intrinsic_drive_per_second"] * dt
        adapt = s["adaptation"]
        if adapt and d["adaptation_tau_seconds"] > 0:
            adapt *= math.exp(-dt / d["adaptation_tau_seconds"])
        thr = d["threshold"] + adapt
        out[uid] = {"activity_pre": act, "threshold_eff": thr, "drive": drive,
                    "fires": s["refractory_remaining"] <= 0 and act >= thr}
    return out


# ---- 1 個体の探索（run.py と通しの確認が同じ関数を使う） ---------------------------------------------

def explore_seed(protocol: dict, seed: int) -> dict:
    end, total, every = experience_end(protocol), total_pulses(protocol), sample_every(protocol)
    if protocol["intervention"]["at"] != INTERVENTION_AT:
        raise ValueError("介入の時点の式が道具と違う")
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
    for c in CONDITIONS:
        out[c]["connections_12000"] = apps[c].connections.export_state()
        out[c]["units_12000"] = unit_states(apps[c])
    # 介入：ordered を 2 つ複製する（介入腕・何も変えない複製）。control は ordered の本体そのもの
    inter, inter_log = clone(apps["ordered"], logs["ordered"])
    twin, twin_log = clone(apps["ordered"], logs["ordered"])
    transplant(inter, units, target_weights(out["shuffled"]["connections_12000"], units))
    fork = {"control": snapshot(apps["ordered"]), "intervention": snapshot(inter)}
    arms = run_arms({"control": (apps["ordered"], logs["ordered"]), "intervention": (inter, inter_log)},
                    end, total, every, units)
    advance_to(twin, total)
    advance_to(apps["shuffled"], total)
    for c in CONDITIONS:
        out[c] |= {"activity": logs[c].activity(), "sensory": logs[c].sensory(),
                   "connections_24000": apps[c].connections.export_state()}
    return {"seed": seed, "first_divergence_history": diverge,
            "roles": {"receptors": role_receptors(protocol, seed), "units": units},
            "conditions": out, "fork": fork,
            "arms": arms | {"connections_24000": {"control": apps["ordered"].connections.export_state(),
                                                  "intervention": inter.connections.export_state()}},
            "twin": {"activity": twin_log.activity(), "connections_24000": twin.connections.export_state()}}
