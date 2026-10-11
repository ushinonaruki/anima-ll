"""実験 0013 の道具（事前登録の一部。測定の前にコミットする）。脳の側ではなく、実験者の側。

- 個体の組み立て：可塑性あり・なしの設計図（protocol の brain）、外からの刺激なし（Receptor なし）
- 適格な組：出生時のばらつきのあとの Unit の値（Pulse 0）で、両方が ρ ≥ 1 の組
- 複製の介入：可塑性ありの個体を複製し、複製の上でだけ 6 本の重みを w0 に戻す（痕跡はそのまま）
- 指標の材料：d ＝ 1 の組の数 F_ij、非対称 f_ij、接続の非対称 a_ij
- 判定の量（C_birth・H_A・M の和）は、項が 0 の組・空の和をふつうの算術で扱う（専用の分岐を置かない）

複製・時間の進め方・来歴のログは、0012 の道具（experiments/0012_passive_world/world.py）をそのまま使う。
"""

import importlib.util
import itertools
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W12 = _load("world_0012_for_0013", ROOT / "experiments/0012_passive_world/world.py")
ExperimentLog = W12.ExperimentLog
clone = W12.clone
advance_to = W12.advance_to
weights_of = W12.weights_of


def manifest_raw(protocol: dict, condition: str) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"][condition]).read_text(encoding="utf-8"))


def build(protocol: dict, condition: str, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment({"runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]}})
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol, condition)),
        env,
        parse_birth_state({"individual_id": f"anima-0013-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        run_metadata={"experiment": "0013", "condition": condition},
    )


def birth_state(app: Application) -> dict:
    """Pulse 0 の Unit の状態（出生時の状態）。"""
    return {u.unit_id: u.export_state() for u in app.units.all()}


def rho(unit_state: Mapping) -> float:
    d = unit_state["dynamics"]
    return d["intrinsic_drive_per_second"] / ((1 - d["decay_per_second"]) * d["threshold"])


def pairs(units: Iterable[str]) -> list[tuple[str, str]]:
    """組 {i, j}（i < j の順で 1 回ずつ）。"""
    return list(itertools.combinations(sorted(units), 2))


def eligible_pairs(birth: Mapping[str, Mapping], units: Iterable[str]) -> list[tuple[str, str]]:
    """両方の Unit が ρ ≥ 1（外からの入力なしに自力で発火できる）組。結果を見る前に、出生時の状態だけで決まる。"""
    return [(i, j) for i, j in pairs(units) if rho(birth[i]) >= 1 and rho(birth[j]) >= 1]


def reset_weights(app: Application, w0: float) -> None:
    """複製の上でだけ使う：可塑性の対象の接続の重みを w0 に戻す。痕跡はそのまま。"""
    state = app.connections.export_state()
    for values in state.values():
        values["weight"] = w0
    app.connections.import_state(state)


def follows(activity: Iterable[list], window: tuple[int, int]) -> dict[tuple[str, str], int]:
    """F_ij：窓 [lo, hi] の中で、i が p − 1 に発火し、j が p に発火した Pulse p の数（d ＝ 1 の組）。"""
    lo, hi = window
    fired: dict[int, set[str]] = {}
    for p, u in activity:
        fired.setdefault(p, set()).add(u)
    counts: dict[tuple[str, str], int] = {}
    for p in range(lo, hi + 1):
        for i in fired.get(p - 1, ()):
            for j in fired.get(p, ()):
                if i != j:
                    counts[(i, j)] = counts.get((i, j), 0) + 1
    return counts


def f_asym(F: Mapping[tuple[str, str], int], i: str, j: str) -> int:
    """f_ij ＝ F_ij − F_ji。"""
    return F.get((i, j), 0) - F.get((j, i), 0)


def a_asym(weights: Mapping[str, float], i: str, j: str) -> float:
    """a_ij ＝ w(i→j) − w(j→i)。"""
    return weights[f"{i}.main->{j}"] - weights[f"{j}.main->{i}"]


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


# ---- 操作の確認（run.py の実行時の確認と、analyze.py の保存データの再検証が同じ関数を使う） ----------------

def first_weight_change(activity: Iterable[list]) -> int | None:
    """最初に重みが変わる Pulse：ある Unit が発火した Pulse p に、別の Unit が p より前に発火していた最初の p。

    そのとき、別の Unit からこの Unit への接続が強まり（痕跡 > 0）、逆向きが弱まる。それより前は、どの接続も変わらない。
    そのような p がなければ None（重みは一度も変わらない）。
    """
    first_fire: dict[str, int] = {}
    for p, u in sorted(map(tuple, activity)):
        if any(q < p for v, q in first_fire.items() if v != u):
            return p
        first_fire.setdefault(u, p)
    return None


def identical_until_first_weight_change(act_p: list, act_n: list) -> bool:
    """README §5.1：可塑性あり・なしの発火の記録が、最初に重みが変わる Pulse まで一致するか。

    最初に重みが変わる Pulse は、可塑性ありの記録から求める。重みが一度も変わらない個体（None）では、
    可塑性は一度も働かないので、全区間の記録が一致しなければならない。
    """
    act_p, act_n = [list(a) for a in act_p], [list(a) for a in act_n]
    first = first_weight_change(act_p)
    if first is None:
        return act_p == act_n
    return [a for a in act_p if a[0] <= first] == [a for a in act_n if a[0] <= first]

