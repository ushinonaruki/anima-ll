"""可塑性 v1.1 の設計案（docs/plasticity-v1.1-scale.md）§3・4 の数値を出す計算。

孤立した 1 Unit（入力なし・順応あり）を、出生時のばらつきの格子（閾値・内在的駆動の ±jitter を GRID × GRID 点）の
各点で動かし、応答の余地 m(t) ＝ (θ ＋ adaptation) − (activity × decay ＋ drive) の分布を求める。
力学の値は config/neuroarchitecture/minimal-v3.yaml から読む。個体の seed は使わない（格子は一様分布の代わり）。

使い方（リポジトリ直下で）: python docs/analysis/plasticity_v1_1_margin.py
"""

import math
from pathlib import Path

import numpy as np
import yaml

GRID = 21
START, END = 600, 15000   # 0012 と同じ「落ち着いたあと」から総 Pulse まで（1 Pulse ＝ 1 秒）

dyn = yaml.safe_load(Path("config/neuroarchitecture/minimal-v3.yaml").read_text(encoding="utf-8"))["defaults"]["dynamics"]
lam, theta, drive0 = dyn["decay"], dyn["threshold"], dyn["intrinsic_drive"]
jit, alpha, tau = dyn["jitter"], dyn["adaptation_increment"], dyn["adaptation_tau"]

margins, regime = [], []
grid = np.linspace(-jit, jit, GRID)
for j2 in grid:
    for j1 in grid:
        th, drive = theta * (1 + j2), drive0 * (1 + j1)
        rho, a_star = drive / ((1 - lam) * th), drive / (1 - lam)
        a = adapt = 0.0
        for t in range(1, END + 1):
            if t >= START:
                margins.append((th + adapt * math.exp(-1 / tau)) - (a * lam + drive))
                regime.append("quiescent" if rho < 1 else ("waiting" if a > 0.99 * a_star else "recovering"))
            a = a * lam + drive
            adapt *= math.exp(-1 / tau)
            if a >= th + adapt:
                a, adapt = 0.0, adapt + alpha
m, r = np.array(margins), np.array(regime)


def p(w: float) -> float:
    return float((m <= w).mean())


print("quantiles 5/25/50/75/95%:", [round(float(np.quantile(m, q)), 4) for q in (0.05, 0.25, 0.5, 0.75, 0.95)])
for name in ("quiescent", "waiting", "recovering"):
    x = m[r == name]
    print(f"{name:10s} share {len(x) / len(m):.2f}  min {x.min():.4f}  median {np.median(x):.4f}  "
          f"p95 {np.quantile(x, 0.95):.4f}  max {x.max():.4f}")
print(f"P0 = {p(0.0):.3f}")
candidates = {"theta": theta, "drive_per_pulse": drive0, "leak_at_threshold": (1 - lam) * theta,
              "nominal_margin": abs(theta - drive0 / (1 - lam)), "alpha": alpha}
for name, w_max in candidates.items():
    print(f"{name:18s} w_max {w_max:.4f}  P(w0) {p(w_max / 2):.3f}  P(w_max) {p(w_max):.3f}  "
          f"branching~2P(w0) {2 * p(w_max / 2):.2f}")
