"""実験 0014 の道具（事前登録 v0.3 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 役の割り当て：A・B・C → receptor.x1〜x3。protocol の role_orders の (seed − 1) mod 6 番目（乱数ではない。0012 と同じ）
- 刺激の列：
  - ordered：試行 k の A を trials.first ＋ k × trials.every に、その b_offset 後に B、c_offset 後に C
  - shuffled：ordered の 600 個の刺激の時刻はそのままで、札を random.Random("0014-shuffle:<seed>") の shuffle で
    時刻のあいだで並べ替える（名前で分けた流れ。Birth State の乱数 random.Random(seed) とは別）
- 試し（README §3.3）：本体の t0 − 1 の終わりから試しの元を複製し、t0 に Receptor A を入れて t0 を処理する。
  t0 の処理の終わりで 2 つの腕（as_is・equalized）に複製し、equalized の 4 本の重みだけを置き直す。
  両腕を t0 ＋ read_at の処理の終わりまで進める。複製でも可塑性は止めない
- 介入：x ＝ w(A→B)、y ＝ w(A→C)、m ＝ (x ＋ y)／2 として w(A→B) ＝ w(A→C) ＝ m、w(B→A) ＝ w(C→A) ＝ w_max − m。
  痕跡・Unit の状態・B–C の 2 本には触らない

複製・時間の進め方・来歴のログ・Receptor は、0012 の道具（experiments/0012_passive_world/world.py）をそのまま使う。
"""

import importlib.util
import random
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ROLES = ("A", "B", "C")

# protocol.yaml の式の文字列。ここに書いた式を実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
RNG_SHUFFLE = "0014-shuffle:{seed}"
PROBE_COUNT = "adaptation_tau / pulse_interval_seconds"
INTERVENTION_RULE = "equalize_ab_ac_weight_contrast_preserving_pair_sums"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W12 = _load("world_0012_for_0014", ROOT / "experiments/0012_passive_world/world.py")
ExperimentLog = W12.ExperimentLog
ScheduledReceptor = W12.ScheduledReceptor
clone = W12.clone
advance_to = W12.advance_to
weights_of = W12.weights_of
connection_id = W12.connection_id


# ---- 設計図と時間の流れ ----------------------------------------------------------------

def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


def w_max(protocol: dict) -> float:
    return parse_neuroarchitecture(manifest_raw(protocol)).plasticity.w_max


def probe_count(protocol: dict) -> int:
    """試しの数 ＝ adaptation_tau ÷ pulse_interval_seconds（τ_a の 1 区間の Pulse の数）。整数でなければ止める。"""
    if protocol["timeline"]["probes"]["count"] != PROBE_COUNT:
        raise ValueError("probes.count の式が道具と違う")
    exact = (manifest_raw(protocol)["defaults"]["dynamics"]["adaptation_tau"]
             / protocol["timeline"]["pulse_interval_seconds"])
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"adaptation_tau ÷ pulse_interval_seconds が整数でない（{exact}）")
    return n


def trial_starts(protocol: dict) -> list[PulseNumber]:
    t = protocol["timeline"]["trials"]
    return [t["first"] + k * t["every"] for k in range(t["count"])]


def probe_times(protocol: dict) -> list[PulseNumber]:
    p = protocol["timeline"]["probes"]
    return [p["first"] + k * p["every"] for k in range(probe_count(protocol))]


def w_post_pulse(protocol: dict) -> PulseNumber:
    """W_post を測る Pulse ＝ probes.first − 1。"""
    return protocol["timeline"]["probes"]["first"] - 1


# ---- 役の割り当てと刺激 ------------------------------------------------------------------

def role_receptors(protocol: dict, seed: int) -> dict[str, ComponentId]:
    order = protocol["stimulus"]["role_orders"][(seed - 1) % 6]
    return dict(zip(ROLES, order))


def role_units(protocol: dict, seed: int) -> dict[str, ComponentId]:
    to_unit = protocol["brain"]["receptors"]
    return {role: to_unit[r] for role, r in role_receptors(protocol, seed).items()}


def ordered_stimuli(protocol: dict) -> list[tuple[PulseNumber, str]]:
    s = protocol["stimulus"]
    out = []
    for start in trial_starts(protocol):
        out += [(start, "A"), (start + s["b_offset"], "B"), (start + s["c_offset"], "C")]
    return sorted(out)


def shuffled_stimuli(protocol: dict, seed: int) -> list[tuple[PulseNumber, str]]:
    ordered = ordered_stimuli(protocol)
    labels = [label for _, label in ordered]
    random.Random(RNG_SHUFFLE.format(seed=seed)).shuffle(labels)
    return [(t, label) for (t, _), label in zip(ordered, labels)]


def stimuli(protocol: dict, condition: str, seed: int) -> list[tuple[PulseNumber, str]]:
    if condition == "ordered":
        return ordered_stimuli(protocol)
    if condition == "shuffled":
        return shuffled_stimuli(protocol, seed)
    raise ValueError(f"未知の条件: {condition}")


def first_divergence(protocol: dict, seed: int) -> PulseNumber | None:
    """2 条件の札が最初に違う Pulse（同じなら None）。"""
    for (t, a), (_, b) in zip(stimuli(protocol, "ordered", seed), stimuli(protocol, "shuffled", seed)):
        if a != b:
            return t
    return None


def receptors_for(protocol: dict, condition: str, seed: int) -> dict[ComponentId, ScheduledReceptor]:
    roles = role_receptors(protocol, seed)
    schedule: dict[ComponentId, list[PulseNumber]] = {r: [] for r in protocol["brain"]["receptors"]}
    for t, label in stimuli(protocol, condition, seed):
        schedule[roles[label]].append(t)
    return {r: ScheduledReceptor(r, pulses) for r, pulses in schedule.items()}


# ---- 個体の組み立て ----------------------------------------------------------------------

def build(protocol: dict, condition: str, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-0014-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=receptors_for(protocol, condition, seed),
        run_metadata={"experiment": "0014", "condition": condition,
                      "receptors": "ScheduledReceptor（experiments/0012_passive_world/world.py）"},
    )


def unit_states(app: Application) -> dict:
    return {u.unit_id: u.export_state() for u in app.units.all()}


def snapshot(app: Application) -> dict:
    """Unit の状態と接続の状態（重み・痕跡）。"""
    return {"units": unit_states(app), "connections": app.connections.export_state()}


# ---- 介入 --------------------------------------------------------------------------------

def four_ids(units: Mapping[str, ComponentId]) -> dict[str, str]:
    a, b, c = units["A"], units["B"], units["C"]
    return {"AB": connection_id(a, b), "AC": connection_id(a, c), "BA": connection_id(b, a), "CA": connection_id(c, a)}


def equalized_weights(weights: Mapping[str, float], units: Mapping[str, ComponentId], w_max_: float) -> dict[str, float]:
    """介入後の 4 本の重み（式だけ。状態には触らない）。"""
    ids = four_ids(units)
    m = (weights[ids["AB"]] + weights[ids["AC"]]) / 2
    return {ids["AB"]: m, ids["AC"]: m, ids["BA"]: w_max_ - m, ids["CA"]: w_max_ - m}


def equalize(app: Application, units: Mapping[str, ComponentId], w_max_: float) -> None:
    """複製の上でだけ使う：4 本の重みを置き直す。痕跡・他の接続・Unit の状態はそのまま。"""
    state = app.connections.export_state()
    for cid, w in equalized_weights({k: v["weight"] for k, v in state.items()}, units, w_max_).items():
        state[cid]["weight"] = w
    app.connections.import_state(state)


def w_difference(weights: Mapping[str, float], units: Mapping[str, ComponentId]) -> float:
    """W ＝ w(A→B) − w(A→C)。"""
    ids = four_ids(units)
    return weights[ids["AB"]] - weights[ids["AC"]]


# ---- 試し --------------------------------------------------------------------------------

def probe(protocol: dict, app: Application, app_log: ExperimentLog, seed: int, t0: PulseNumber,
          deliver: bool = True) -> dict:
    """本体は t0 − 1 まで進んでいること。本体には触らない。

    deliver は契約テストのためだけにある（False：A の刺激を入れない。本番の run.py は常に True）。
    返す値：
      base_sensory  試しの元が t0 に受けた感覚の出来事 [[Pulse, Receptor]]
      fork          2 腕の分けた直後の状態 {as_is, equalized: {units, connections}}
      activity      2 腕の発火 {as_is, equalized: [[Pulse, Unit]]}（t0 ＋ 1〜t0 ＋ read_at）
    """
    if app.lifecycle.pulse != t0 - 1:
        raise ValueError(f"試しは Pulse {t0 - 1} まで進んだ個体から作る（今 {app.lifecycle.pulse}）")
    units = role_units(protocol, seed)
    base, base_log = clone(app, app_log)
    if deliver:
        base.receptors[role_receptors(protocol, seed)["A"]].inject(t0)
    advance_to(base, t0 + protocol["probe"]["fork_after"])
    as_is, log_as_is = clone(base, base_log)
    eq, log_eq = clone(base, base_log)
    equalize(eq, units, w_max(protocol))
    fork = {"as_is": snapshot(as_is), "equalized": snapshot(eq)}
    end = t0 + protocol["probe"]["read_at"]
    advance_to(as_is, end)
    advance_to(eq, end)
    return {"t0": t0, "base_sensory": base_log.sensory(), "fork": fork,
            "activity": {"as_is": log_as_is.activity(), "equalized": log_eq.activity()}}


def fired_at(activity: Iterable[list], unit: ComponentId, pulse: PulseNumber) -> int:
    return int(any(p == pulse and u == unit for p, u in activity))


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


def delta_r(probe_record: Mapping, units: Mapping[str, ComponentId], read_at: int) -> int:
    """ΔR(t0) ＝ [B − C](as_is) − [B − C](equalized)。B・C は t0 ＋ read_at に発火したら 1。"""
    t = probe_record["t0"] + read_at
    r = {arm: fired_at(act, units["B"], t) - fired_at(act, units["C"], t)
         for arm, act in probe_record["activity"].items()}
    return r["as_is"] - r["equalized"]


def w_probe(probe_record: Mapping, units: Mapping[str, ComponentId]) -> float:
    """W_probe(t0)：介入の直前の重みの差（as_is の腕の分けた直後の重み）。"""
    return w_difference({k: v["weight"] for k, v in probe_record["fork"]["as_is"]["connections"].items()}, units)


# ---- 操作の確認（run.py の実行時と analyze.py の再検証が同じ関数を使う） ----------------------

def check_stimulus_counts(protocol: dict, seed: int, sensory: Mapping[str, list]) -> list[str]:
    """刺激の列と、本体が受けた感覚の出来事の両方で、A・B・C が各 counts、時刻の集合が 2 条件で同じ、順序ありの形。"""
    problems = []
    s = protocol["stimulus"]
    to_role = {r: role for role, r in role_receptors(protocol, seed).items()}
    times = {}
    for cond in protocol["stimulus"]["conditions"]:
        planned = stimuli(protocol, cond, seed)
        got = sorted((p, to_role[r]) for p, r in sensory[cond])
        if got != sorted(planned):
            problems.append(f"{cond}: 本体が受けた感覚の出来事が刺激の列と違う")
        for role in ROLES:
            if sum(1 for _, x in got if x == role) != s["counts"][role]:
                problems.append(f"{cond}: {role} の数が {s['counts'][role]} ではない")
        times[cond] = sorted(p for p, _ in got)
        if len(set(times[cond])) != len(times[cond]):
            problems.append(f"{cond}: 同じ Pulse に 2 つの刺激がある")
    if len(set(map(tuple, times.values()))) != 1:
        problems.append("刺激の時刻の集合が 2 条件で違う")
    at = {p: x for p, x in ((p, to_role[r]) for p, r in sensory["ordered"])}
    for p, x in at.items():
        if x == "A" and (at.get(p + s["b_offset"]) != "B" or at.get(p + s["c_offset"]) != "C"):
            problems.append(f"ordered: A({p}) の後の B・C の形が違う")
            break
    return problems


def check_probe(protocol: dict, seed: int, record: Mapping, w_max_: float, tol: float = 1e-12) -> list[str]:
    """1 回の試しの操作の確認（試しの入力・介入の複製・2 腕の t0 ＋ 1 の一致）。"""
    problems = []
    t0 = record["t0"]
    units = role_units(protocol, seed)
    a_rec = role_receptors(protocol, seed)["A"]
    if [list(x) for x in record["base_sensory"]] != [[t0, a_rec]]:
        problems.append(f"t0 {t0}: 試しの元の感覚の出来事が A の 1 つだけではない")
    f_as, f_eq = record["fork"]["as_is"], record["fork"]["equalized"]
    if f_as["units"] != f_eq["units"]:
        problems.append(f"t0 {t0}: 2 腕の Unit の状態が違う")
    ids = four_ids(units)
    w_as = {k: v["weight"] for k, v in f_as["connections"].items()}
    w_eq = {k: v["weight"] for k, v in f_eq["connections"].items()}
    expected = equalized_weights(w_as, units, w_max_)
    for cid, v in f_as["connections"].items():
        e = f_eq["connections"][cid]
        if e["pre_trace"] != v["pre_trace"] or e["post_trace"] != v["post_trace"]:
            problems.append(f"t0 {t0}: {cid} の痕跡が変わった")
        if cid not in expected and e["weight"] != v["weight"]:
            problems.append(f"t0 {t0}: 対象外の {cid} の重みが変わった")
    if any(abs(w_eq[c] - w) > tol for c, w in expected.items()):
        problems.append(f"t0 {t0}: 4 本の重みが式どおりでない")
    for x, y in (("AB", "BA"), ("AC", "CA")):
        if abs(w_eq[ids[x]] + w_eq[ids[y]] - w_max_) > tol:
            problems.append(f"t0 {t0}: 組 {x} の和が w_max でない")
    a = lambda w, x, y: w[ids[x]] - w[ids[y]]
    if abs((a(w_eq, "AB", "BA") + a(w_eq, "AC", "CA")) - (a(w_as, "AB", "BA") + a(w_as, "AC", "CA"))) > tol:
        problems.append(f"t0 {t0}: a_AB ＋ a_AC が介入の前後で変わった")
    t1 = t0 + 1
    if ([x for x in record["activity"]["as_is"] if x[0] == t1]
            != [x for x in record["activity"]["equalized"] if x[0] == t1]):
        problems.append(f"t0 {t0}: 2 腕の t0 ＋ 1 の発火が違う")
    return problems
