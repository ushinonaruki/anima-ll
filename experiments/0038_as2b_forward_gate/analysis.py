"""実験 0038（AS2b の前方の関門）の解析の部分：孤立した Unit の内在の発火の間隔（命題 T-5）。

docs/as2b-minimal-implementation-contract.md §7.3（②a）。seed・乱数・既存の raw は使わない。C0 の設計図
（experiments/0012_passive_world/neuroarchitecture.yaml）の力学の値と、出生時のばらつきの幅（jitter）だけから計算する。

- 閉じた形：A ＝ c／(1 − λ)（Δt ＝ 1。入力のない活動の行き着く値）。A ≤ θ なら、入力のない Unit は発火しない
- 格子の反復：(θ, c) の出生時の範囲を等間隔の格子で覆い、各点で SimpleActivityDynamics をそのまま反復して、
  入力のない Unit の発火の間隔（はじめの間隔と、順応が積もった後の間隔）を数える（決定論。乱数なし）
- 窓の長さ W：手がかりの Unit の 1 回の駆動が源の活動に残す割合 λ^n が 0.05 以下になる最小の n
"""

import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from anima_ll.unit.dynamics.activity_dynamics import ActivityState  # noqa: E402
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics  # noqa: E402

C0_MANIFEST = ROOT / "experiments" / "0012_passive_world" / "neuroarchitecture.yaml"
RESIDUAL = 0.05          # 窓の長さの基準：1 回の駆動の残りが 5 % 以下になるまで
GRID = 60                # 格子の一辺（θ と c の各範囲を GRID 等分した中点）
HORIZON = 6000           # 格子の各点で反復する Pulse の数（τ_a ＝ 300 の 20 倍）
LATE = 3                 # 「順応が積もった後」の間隔として見る、最後の間隔の数


def c0_dynamics() -> dict:
    raw = yaml.safe_load(C0_MANIFEST.read_text(encoding="utf-8"))
    d = raw["defaults"]["dynamics"]
    return {"decay": float(d["decay"]), "threshold": float(d["threshold"]), "intrinsic_drive": float(d["intrinsic_drive"]),
            "jitter": float(d["jitter"]), "refractory_pulses": int(d["refractory_pulses"]),
            "initial_activity_max_ratio": float(d["initial_activity_max_ratio"]),
            "adaptation_increment": float(d["adaptation_increment"]), "adaptation_tau": float(d["adaptation_tau"])}


def ranges(p: dict) -> dict:
    j = p["jitter"]
    return {"threshold": (p["threshold"] * (1 - j), p["threshold"] * (1 + j)),
            "intrinsic_drive": (p["intrinsic_drive"] * (1 - j), p["intrinsic_drive"] * (1 + j))}


def silent_probability(p: dict) -> float:
    """P(A ≤ θ)：θ と c が出生時の範囲で独立に一様なとき（bootstrap の vary）、入力のない Unit が発火しない割合（閉じた形）。"""
    (t0, t1), (c0, c1) = ranges(p)["threshold"], ranges(p)["intrinsic_drive"]
    a0, a1 = c0 / (1 - p["decay"]), c1 / (1 - p["decay"])
    # A ~ U[a0, a1]、θ ~ U[t0, t1]。∫∫ 1[A ≤ θ] を、θ ごとの F_A(θ) の平均として求める
    def cdf_a(x: float) -> float:
        return min(1.0, max(0.0, (x - a0) / (a1 - a0)))
    lo, hi = max(t0, a0), min(t1, a1)
    if hi <= lo:
        inside = 0.0
    else:
        inside = ((hi - a0) ** 2 - (lo - a0) ** 2) / (2 * (a1 - a0))     # ∫_{lo}^{hi} (θ − a0)/(a1 − a0) dθ
    above = max(0.0, t1 - max(a1, t0))                                   # θ > a1 では F_A ＝ 1
    return (inside + above) / (t1 - t0)


def isolated_intervals(p: dict, threshold: float, drive: float, horizon: int = HORIZON) -> list[int]:
    dyn = SimpleActivityDynamics(decay_per_second=p["decay"], threshold=threshold, refractory_pulses=p["refractory_pulses"],
                                 intrinsic_drive_per_second=drive, adaptation_increment=p["adaptation_increment"],
                                 adaptation_tau_seconds=p["adaptation_tau"])
    state, fires = ActivityState(), []          # 出生時の activity が最も低い 0 から（はじめの間隔の下限になる）
    for t in range(1, horizon + 1):
        state, firing = dyn.advance(state, 0.0, 1.0)
        if firing is not None:
            fires.append(t)
    return [b - a for a, b in zip(fires, fires[1:])], fires


def reset_interval_lower_bound(p: dict) -> int:
    """発火して activity が 0 に戻った後、次の発火までの Pulse 数の下限（順応 0・θ 最小・c 最大の角。閉じた形）。

    activity(n) ＝ A(1 − λ^n) なので、A(1 − λ^n) ≥ θ となる最小の n。順応（> 0）があれば、これより長くなる。
    """
    (t0, _t1), (_c0, c1) = ranges(p)["threshold"], ranges(p)["intrinsic_drive"]
    a_max = c1 / (1 - p["decay"])
    return math.ceil(math.log(1 - t0 / a_max) / math.log(p["decay"]) - 1e-12)


def window_length(p: dict, residual: float = RESIDUAL) -> int:
    return math.ceil(math.log(residual) / math.log(p["decay"]))


def proposition() -> dict:
    p = c0_dynamics()
    (t0, t1), (c0, c1) = ranges(p)["threshold"], ranges(p)["intrinsic_drive"]
    first, late, silent = [], [], 0
    for i in range(GRID):
        th = t0 + (i + 0.5) * (t1 - t0) / GRID
        for j in range(GRID):
            c = c0 + (j + 0.5) * (c1 - c0) / GRID
            intervals, fires = isolated_intervals(p, th, c)
            if not fires:
                silent += 1
                continue
            first.append(fires[0])
            if len(intervals) >= LATE:
                late.append(min(intervals[-LATE:]))
    late.sort()

    def q(xs, f):
        return xs[int(f * (len(xs) - 1))]

    return {
        "c0_dynamics": p,
        "ranges": {k: list(v) for k, v in ranges(p).items()},
        "A_range": [c0 / (1 - p["decay"]), c1 / (1 - p["decay"])],
        "silent_probability_closed_form": silent_probability(p),
        "reset_interval_lower_bound": reset_interval_lower_bound(p),
        "grid": {"side": GRID, "horizon": HORIZON, "late_intervals_used": LATE,
                 "silent_fraction": silent / GRID ** 2,
                 "first_firing_min": min(first),
                 "late_interval_min": late[0],
                 "late_interval_quantiles": {str(f): q(late, f) for f in (0.1, 0.25, 0.5, 0.75, 0.9)}},
        "window_length_W": window_length(p),
        "residual_at_W": p["decay"] ** window_length(p),
    }


if __name__ == "__main__":
    print(json.dumps(proposition(), ensure_ascii=False, indent=2))
